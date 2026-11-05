"""RemoteIntercom provisioning server for ESP8266 MicroPython."""

import gc
import os
import socket
import sys
import time
from typing import TYPE_CHECKING

import config
import machine
import network
import uasyncio as asyncio
import ubinascii
import urandom
import utils
from http_io import TEMPLATE_DIR, HTTPClient, parse_form, send, send_bytes, send_file, send_headers

if TYPE_CHECKING:
    # Opaque tick types exist only in the MicroPython stubs.
    from _mpy_shed.time_mp import _TicksMs


HTTP_HOST = "0.0.0.0"
HTTP_PORT = 80
CONNECT_TIMEOUT_MS = 15 * 1000
HEARTBEAT_INTERVAL_MS = 30 * 1000
SUCCESS_GRACE_MS = 5 * 1000
SUCCESS_MAX_GRACE_MS = 60 * 1000
RETRY_INITIAL_MS = 5 * 1000
RETRY_MAX_MS = 60 * 1000
REQUEST_TIMEOUT_MS = 10 * 1000
MAINTENANCE_INTERVAL_MS = 20
MAX_CLIENTS = 2
SESSION_LIFETIME_MS = 30 * 60 * 1000
MAX_SESSIONS = 4
# TCP may split one HTTP request across several recv calls.  The ESP8266 has a
# very small heap, so keep the header limit modest rather than accumulating a
# browser-sized request indefinitely.
MAX_HEADER_BYTES = 1024
MAX_BODY_BYTES = 1024
SSID_PLACEHOLDER = b"{{ssid}}"
# GPIO0 is the FLASH button on many ESP8266 development boards.  The button
# must be pressed after boot: holding GPIO0 low while resetting enters ROM
# flashing mode instead of starting MicroPython.
ADMIN_RESET_PIN = 0
ADMIN_RESET_HOLD_MS = 5 * 1000
DOOR_RELAY_PIN = 4
DOORBELL_PIN = 5
RELAY_PULSE_MS = 1000
DOOR_COOLDOWN_MS = 5000
DOORBELL_DEBOUNCE_MS = 50
DOORBELL_BROADCAST_INTERVAL_MS = 200
DOORBELL_BROADCAST_COUNT = 3
DOORBELL_PORT = 31941
DOORBELL_ADDRESS = "255.255.255.255"


def ap_name(ap: network.WLAN) -> str:
    mac = ap.config("mac")
    suffix = int(ubinascii.hexlify(mac[-3:]).decode("ascii"), 16) % 10000
    return f"RemoteIntercom{suffix:04d}"


def restore_admin_password(cfg: "config.Config") -> None:
    """Restore only the administrator login; preserve saved Wi-Fi details."""
    salt = utils.new_salt()
    cfg["password_salt"] = salt
    cfg["password_hash"] = utils.password_digest("admin", salt)
    cfg["must_change_password"] = True
    config.save_config(cfg)


class IntercomServer:
    def __init__(self) -> None:
        self.door_relay = machine.Pin(DOOR_RELAY_PIN, machine.Pin.OUT, value=1)
        self.doorbell = machine.Pin(DOORBELL_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        self.relay_deadline: _TicksMs | None = None
        self.door_cooldown: _TicksMs | None = None
        self.doorbell_raw = self.doorbell.value()
        self.doorbell_stable = self.doorbell_raw
        print(
            "Intercom relay GPIO", DOOR_RELAY_PIN, "HIGH; doorbell GPIO", DOORBELL_PIN,
            self.doorbell_raw,
        )
        self.doorbell_changed = time.ticks_ms()
        self.broadcast_remaining = 0
        self.broadcast_deadline: _TicksMs | None = None
        self.config: config.Config = config.load_config()
        self.ap = network.WLAN(network.AP_IF)
        self.sta = network.WLAN(network.STA_IF)
        # The ESP8266 may restore a saved station connection before main.py
        # runs. Restart it so the new DHCP request carries our hostname.
        if self.sta.active():
            self.sta.active(False)
        network.hostname(ap_name(self.ap))
        self.sessions: dict[str, _TicksMs] = {}
        # Firmware can restore an AP before main.py; turn it off explicitly.
        self.ap.active(False)
        self.ap_running = False
        self.boot_connecting = bool(self.config["wifi_ssid"])
        self.connect_started: _TicksMs | None = None
        self.connect_requested = bool(self.config["wifi_ssid"])
        self.reset_station = False
        self.retry_deadline: _TicksMs | None = None
        self.retry_delay = RETRY_INITIAL_MS
        self.restart_owner: HTTPClient | None = None
        self.active_clients = 0
        self.was_connected = False
        self.provisioning = False
        self.connection_result: str | None = None
        self.shutdown_deadline: _TicksMs | None = None
        self.next_heartbeat = time.ticks_add(time.ticks_ms(), HEARTBEAT_INTERVAL_MS)
        self.reset_button = machine.Pin(ADMIN_RESET_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        self.reset_started: _TicksMs | None = None
        self.reset_latched = False
        # Serial logs retain no history; only these fixed-size counters persist.
        self.request_count = 0

    def start_ap(self) -> None:
        if self.ap_running:
            return
        self.ap.active(True)
        self.ap.config(essid=ap_name(self.ap), authmode=network.AUTH_OPEN)
        self.ap_running = True
        print("Provisioning AP:", ap_name(self.ap), "at", self.ap.ifconfig()[0])

    def stop_ap(self) -> None:
        if self.ap_running:
            self.ap.active(False)
            self.ap_running = False
            print("Home Wi-Fi connected; provisioning AP stopped")

    def finish_wifi_retry(self, now: "_TicksMs", connected: bool) -> None:
        station_status: int | str
        try:
            station_status = self.sta.status()
        except OSError as error:
            station_status = "unknown"
            print("Wi-Fi status error:", error)
        print(
            "Wi-Fi retry end",
            time.ticks_diff(now, self.connect_started) if self.connect_started is not None else 0,
            "ms, status",
            station_status,
            "connected",
            connected,
            "free",
            gc.mem_free(),
        )
        self.connect_started = None
        self.boot_connecting = False
        if connected:
            self.retry_deadline = None
            self.retry_delay = RETRY_INITIAL_MS
            if self.provisioning:
                self.connection_result = "success"
                self.shutdown_deadline = time.ticks_add(now, SUCCESS_MAX_GRACE_MS)
                print("Home Wi-Fi connected; AP grace period started")
        else:
            self.start_ap()
            self.retry_deadline = time.ticks_add(now, self.retry_delay)
            self.retry_delay = min(self.retry_delay * 2, RETRY_MAX_MS)
            try:
                self.sta.active(False)
                print("Wi-Fi station paused; AP remains active")
            except OSError as error:
                print("Wi-Fi station pause error:", error)
            if self.provisioning:
                self.connection_result = "failed"
                self.provisioning = False

    def maintain_wifi(self) -> None:
        now = time.ticks_ms()
        # Settings must be acknowledged before changing the radio connection.
        if self.reset_station and self.restart_owner is not None:
            return
        if self.reset_station:
            self.boot_connecting = False
            self.reset_station = False
            self.connect_started = None
            self.was_connected = False
            try:
                self.sta.active(False)
            except OSError as error:
                print("Wi-Fi station reset error:", error)
            self.start_ap()
        if self.sta.isconnected():
            self.was_connected = True
            if self.connect_started is not None:
                self.finish_wifi_retry(now, True)
            if self.config["must_change_password"]:
                self.shutdown_deadline = None
                self.start_ap()
            elif self.shutdown_deadline is not None and utils.ticks_expired(
                now, self.shutdown_deadline
            ):
                self.provisioning = False
                self.connection_result = None
                self.shutdown_deadline = None
                self.stop_ap()
            elif self.provisioning:
                self.start_ap()
            else:
                self.stop_ap()
            return
        if self.was_connected:
            self.was_connected = False
            self.connect_requested = bool(self.config["wifi_ssid"])
            self.retry_deadline = None
            self.retry_delay = RETRY_INITIAL_MS
            if self.provisioning:
                self.connection_result = "failed"
            else:
                self.connection_result = None
            self.provisioning = False
            self.shutdown_deadline = None
            print("Home Wi-Fi lost; provisioning AP restored")
        # Only the first saved-network attempt starts with the AP disabled.
        if not self.boot_connecting:
            self.start_ap()
        # There is no saved network on a factory-fresh unit.  It should remain
        # available immediately instead of waiting through a pointless retry.
        if not self.config["wifi_ssid"]:
            if self.sta.active():
                try:
                    self.sta.active(False)
                except OSError as error:
                    print("Wi-Fi station pause error:", error)
            return
        if self.connect_started is not None:
            if time.ticks_diff(now, self.connect_started) >= CONNECT_TIMEOUT_MS:
                self.finish_wifi_retry(now, False)
            return
        if self.connect_requested or (
            self.retry_deadline is not None and utils.ticks_expired(now, self.retry_deadline)
        ):
            self.retry_deadline = None
            self.connect_requested = False
            print("Wi-Fi retry start", now, "free", gc.mem_free())
            self.connect_started = now
            try:
                self.sta.active(True)
                self.sta.disconnect()
                self.sta.connect(self.config["wifi_ssid"], self.config["wifi_password"])
            except OSError as error:
                print("Wi-Fi retry error:", error)
                self.finish_wifi_retry(time.ticks_ms(), False)

    def check_admin_reset_button(self) -> None:
        """Reset the admin password after a deliberate five-second press."""
        if self.reset_button.value():
            self.reset_started = None
            self.reset_latched = False
            return
        if self.reset_latched:
            return
        now = time.ticks_ms()
        if self.reset_started is None:
            self.reset_started = now
            return
        if time.ticks_diff(now, self.reset_started) >= ADMIN_RESET_HOLD_MS:
            self.boot_connecting = False
            self.start_ap()
            restore_admin_password(self.config)
            self.sessions = {}
            self.reset_latched = True
            print("Admin password reset to 'admin'; complete setup again")

    def make_session(self) -> str:
        # Sessions are the only long-lived request data. Bound their heap use.
        if len(self.sessions) >= MAX_SESSIONS:
            self.sessions.clear()
        token = f"{urandom.getrandbits(32):08x}{urandom.getrandbits(32):08x}"
        self.sessions[token] = time.ticks_add(time.ticks_ms(), SESSION_LIFETIME_MS)
        return token

    def authenticated(self, headers: dict[str, str]) -> bool:
        cookie = headers.get("cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("session="):
                token = part[8:]
                deadline = self.sessions.get(token)
                if deadline is not None and not utils.ticks_expired(time.ticks_ms(), deadline):
                    return True
                self.sessions.pop(token, None)
        return False

    async def send_admin_page(self, client: HTTPClient) -> None:
        # The SSID is inserted into one attribute; keep the template streamed.
        ssid = self.config["wifi_ssid"]
        ssid = ssid.replace("&", "&amp;").replace('"', "&quot;")
        encoded_ssid = ssid.replace("<", "&lt;").replace(">", "&gt;").encode("utf-8")
        filename = TEMPLATE_DIR + "/admin.html"
        try:
            length = os.stat(filename)[6] - len(SSID_PLACEHOLDER) + len(encoded_ssid)
            if not await send_headers(client, "200 OK", length):
                return
            gc.collect()
            with open(filename, "rb") as handle:  # noqa: ASYNC230 - MicroPython flash API is synchronous
                while True:
                    line = handle.readline()
                    if not line:
                        return
                    if not await send_bytes(client, line.replace(SSID_PLACEHOLDER, encoded_ssid)):
                        return
        except OSError as error:
            print("HTTP", client.request_count, "admin file error:", error)

    async def handle(self, client: HTTPClient) -> None:
        # The request arrives after templates/configuration may have left
        # short-lived objects behind; reclaim them before allocating a buffer.
        gc.collect()
        read_started = time.ticks_ms()
        try:
            # recv() returns whatever TCP has received so far, not one complete
            # HTTP request.  In particular, Mobile Safari commonly sends the
            # form body in a later packet than the headers.
            request = await client.recv(MAX_HEADER_BYTES)
            if not request:
                print("HTTP", client.request_count, "closed before request")
                return
            while b"\r\n\r\n" not in request:
                chunk = await client.recv(128)
                if not chunk:
                    print("HTTP", client.request_count, "closed during headers", len(request))
                    return
                request += chunk
                if b"\r\n\r\n" not in request and len(request) > MAX_HEADER_BYTES:
                    print("HTTP", client.request_count, "headers too large", len(request))
                    return

            header_end = request.find(b"\r\n\r\n")
            if header_end > MAX_HEADER_BYTES:
                print("HTTP", client.request_count, "headers too large", header_end)
                return
            line_end = request.find(b"\r\n")
            first_space = request.find(b" ", 0, line_end)
            second_space = request.find(b" ", first_space + 1, line_end)
            method = request[:first_space]
            path = request[first_space + 1 : second_space]

            content_length = 0
            cookie = ""
            index = line_end + 2
            while index < header_end:
                next_line = request.find(b"\r\n", index, header_end)
                if next_line < 0:
                    next_line = header_end
                if request.startswith(b"Content-Length: ", index):
                    content_length = int(request[index + 16 : next_line])
                elif request.startswith(b"Cookie: ", index):
                    cookie = request[index + 8 : next_line].decode("utf-8")
                index = next_line + 2
            if content_length < 0 or content_length > MAX_BODY_BYTES:
                print("HTTP", client.request_count, "body too large", content_length)
                return
            body_bytes = request[header_end + 4 :]
            while len(body_bytes) < content_length:
                chunk = await client.recv(content_length - len(body_bytes))
                if not chunk:
                    print("HTTP", client.request_count, "closed during body", len(body_bytes))
                    return
                body_bytes += chunk
            if len(body_bytes) > content_length:
                body_bytes = body_bytes[:content_length]
            # All routing information has been extracted; release the larger
            # browser-header buffer before parsing the form body as bytes.
            del request
            gc.collect()
            body = body_bytes
            del body_bytes
        except (OSError, ValueError, UnicodeError) as error:
            # This is intentionally logged: otherwise a malformed or
            # unexpectedly fragmented browser request is indistinguishable
            # from an AP/network failure at the phone.
            print("HTTP", client.request_count, "request error:", error)
            return

        print(
            "HTTP",
            client.request_count,
            method,
            path[:64],
            "header",
            header_end,
            "body",
            content_length,
            "read",
            time.ticks_diff(time.ticks_ms(), read_started),
            "ms",
        )

        logged_in = self.authenticated({"cookie": cookie})
        if path == b"/open":
            if method != b"POST":
                await send(client, "405 Method Not Allowed", "", "Allow:POST\r\n")
            elif self.config["must_change_password"]:
                await send(client, "403 Forbidden", "")
            else:
                now = time.ticks_ms()
                if self.door_cooldown is not None and not utils.ticks_expired(
                    now, self.door_cooldown
                ):
                    await send(client, "429 Too Many Requests", "")
                else:
                    self.door_relay.value(0)
                    self.relay_deadline = time.ticks_add(now, RELAY_PULSE_MS)
                    self.door_cooldown = time.ticks_add(now, DOOR_COOLDOWN_MS)
                    await send(client, "204 No Content", "")
        elif method == b"POST" and path == b"/login":
            values = parse_form(body)
            if (
                utils.password_digest(values.get("password", ""), self.config["password_salt"])
                == self.config["password_hash"]
            ):
                print("HTTP", client.request_count, "login accepted")
                if self.config["must_change_password"]:
                    target = "/setup"
                elif self.provisioning:
                    target = "/connecting"
                elif not self.sta.isconnected():
                    target = "/admin#connection-lost"
                else:
                    target = "/admin"
                await send(
                    client,
                    "303",
                    "",
                    f"Set-Cookie:session={self.make_session()};Path=/\r\nLocation:{target}\r\n",
                )
            else:
                print("HTTP", client.request_count, "login rejected")
                await send(client, "303 See Other", "", "Location:/#incorrect-password\r\n")
        elif not logged_in:
            # This is an HTML form, not an HTTP authentication challenge.
            await send_file(client, "200 OK", "login.html")
        elif method == b"POST" and path in (b"/setup", b"/admin"):
            initial = self.config["must_change_password"]
            if (path == b"/setup") != initial:
                await send(client, "303 See Other", "", "Location:/\r\n")
                return
            values = parse_form(body)
            password = values.get("admin_password", "")
            ssid = values.get("ssid", "")
            wifi_password = values.get("wifi_password", "")
            invalid_password = (initial and len(password) < 8) or (password and len(password) < 8)
            if (
                invalid_password
                or len(password) > 128
                or not ssid
                or len(ssid.encode("utf-8")) > 32
                or len(wifi_password.encode("utf-8")) > 63
            ):
                print("HTTP", client.request_count, "settings rejected")
                target = "/setup#invalid-setup" if initial else "/admin#invalid-settings"
                await send(client, "303 See Other", "", "Location:" + target + "\r\n")
                return
            if not wifi_password and ssid == self.config["wifi_ssid"]:
                wifi_password = self.config["wifi_password"]
            network_changed = (
                ssid != self.config["wifi_ssid"] or wifi_password != self.config["wifi_password"]
            )
            if password:
                salt = utils.new_salt()
                self.config["password_salt"] = salt
                self.config["password_hash"] = utils.password_digest(password, salt)
            self.config["must_change_password"] = False
            self.config["wifi_ssid"] = ssid
            self.config["wifi_password"] = wifi_password
            config.save_config(self.config)
            print("HTTP", client.request_count, "settings saved")
            if initial or network_changed or not self.sta.isconnected():
                # Reset after the response has been sent and the socket closed.
                self.reset_station = True
                self.restart_owner = client
                self.connect_requested = True
                self.retry_deadline = None
                self.retry_delay = RETRY_INITIAL_MS
                self.provisioning = True
                self.connection_result = None
                self.shutdown_deadline = None
                del values, body, password, ssid, wifi_password
                gc.collect()
                await send(client, "303 See Other", "", "Location:/connecting\r\n")
            else:
                await send(client, "303 See Other", "", "Location:/admin#settings-saved\r\n")
        elif path == b"/connecting":
            if self.connection_result == "success":
                if await send_file(client, "200 OK", "success.html"):
                    deadline = time.ticks_add(time.ticks_ms(), SUCCESS_GRACE_MS)
                    if (
                        self.shutdown_deadline is not None
                        and time.ticks_diff(deadline, self.shutdown_deadline) < 0
                    ):
                        self.shutdown_deadline = deadline
            elif self.connection_result == "failed":
                await send(client, "303 See Other", "", "Location:/admin#connection-failed\r\n")
            elif self.provisioning:
                await send_file(client, "200 OK", "connecting.html")
            else:
                await send(client, "303 See Other", "", "Location:/admin\r\n")
        elif self.config["must_change_password"]:
            await send_file(client, "200 OK", "setup.html")
        elif path == b"/setup":
            await send(client, "303 See Other", "", "Location:/admin\r\n")
        elif path == b"/admin":
            await self.send_admin_page(client)
        elif self.provisioning:
            await send(client, "303 See Other", "", "Location:/connecting\r\n")
        else:
            await send(client, "303 See Other", "", "Location:/admin\r\n")

    def maintain_intercom(self, now: "_TicksMs") -> None:
        if self.relay_deadline is not None and utils.ticks_expired(now, self.relay_deadline):
            self.door_relay.value(1)
            self.relay_deadline = None
        if self.door_cooldown is not None and utils.ticks_expired(now, self.door_cooldown):
            self.door_cooldown = None

        level = self.doorbell.value()
        if level != self.doorbell_raw:
            self.doorbell_raw = level
            self.doorbell_changed = now
        elif (
            level != self.doorbell_stable
            and time.ticks_diff(now, self.doorbell_changed) >= DOORBELL_DEBOUNCE_MS
        ):
            self.doorbell_stable = level
            print("Doorbell GPIO", DOORBELL_PIN, level, "STA connected", self.sta.isconnected())
            if not level:
                self.broadcast_remaining = DOORBELL_BROADCAST_COUNT
                self.broadcast_deadline = now

        if (
            self.broadcast_remaining
            and self.broadcast_deadline is not None
            and utils.ticks_expired(now, self.broadcast_deadline)
        ):
            self.broadcast_remaining -= 1
            self.broadcast_deadline = time.ticks_add(now, DOORBELL_BROADCAST_INTERVAL_MS)
            sock = None
            stage = "socket"
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                stage = "setsockopt"
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                stage = "address"
                if sys.platform == "esp8266":
                    # lwIP accepts numeric address tuples directly; resolving the
                    # limited broadcast address may return a negative DNS error.
                    address = (DOORBELL_ADDRESS, DOORBELL_PORT)
                else:
                    address = socket.getaddrinfo(DOORBELL_ADDRESS, DOORBELL_PORT)[0][-1]
                stage = "sendto"
                sent = sock.sendto(b"doorbell", address)
                print("Doorbell UDP sent", sent, "bytes to", DOORBELL_ADDRESS, DOORBELL_PORT)
            except (OSError, ValueError, AttributeError) as error:
                print("Doorbell broadcast error", stage, error)
            finally:
                if sock is not None:
                    sock.close()

    def service(self) -> None:
        now = time.ticks_ms()
        self.maintain_intercom(now)
        self.check_admin_reset_button()
        self.maintain_wifi()
        if utils.ticks_expired(now, self.next_heartbeat):
            self.next_heartbeat = time.ticks_add(now, HEARTBEAT_INTERVAL_MS)
            print(
                "Alive",
                now,
                "AP",
                self.ap_running,
                "STA",
                self.sta.isconnected(),
                "free",
                gc.mem_free(),
            )

    async def maintain_device(self) -> None:
        while True:
            self.service()
            await asyncio.sleep_ms(MAINTENANCE_INTERVAL_MS)

    async def serve_client(
        self, reader: "asyncio.StreamReader", writer: "asyncio.StreamWriter"
    ) -> None:
        # Check before the first await: excess connections allocate no handler
        # buffers and never wait in an unbounded application queue.
        if self.active_clients >= MAX_CLIENTS:
            writer.close()
            await writer.wait_closed()
            return
        self.active_clients += 1
        self.request_count = (self.request_count + 1) % 10000
        client = None
        started = time.ticks_ms()
        try:
            client = HTTPClient(reader, writer, self.request_count)
            print("HTTP", client.request_count, "accepted at", started, "free", gc.mem_free())
            # One budget covers headers, body and response, including trickles.
            await asyncio.wait_for_ms(self.handle(client), REQUEST_TIMEOUT_MS)
        except asyncio.TimeoutError:
            print("HTTP request deadline exceeded")
        except Exception as error:  # noqa: BLE001
            sys.print_exception(error)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            finally:
                if client is not None and self.restart_owner is client:
                    self.restart_owner = None
                self.active_clients -= 1
                if client is not None:
                    print(
                        "HTTP",
                        client.request_count,
                        "done",
                        client.response_status,
                        client.bytes_sent,
                        "bytes",
                        time.ticks_diff(time.ticks_ms(), started),
                        "ms, send_failed",
                        client.send_failed,
                    )
                gc.collect()

    async def run_async(self) -> None:
        listener = await asyncio.start_server(
            self.serve_client, HTTP_HOST, HTTP_PORT, backlog=MAX_CLIENTS
        )
        print("HTTP server listening on port", HTTP_PORT)
        try:
            await self.maintain_device()
        finally:
            listener.close()
            await listener.wait_closed()

    def run(self) -> None:
        asyncio.run(self.run_async())
