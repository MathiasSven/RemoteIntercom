"""Deterministic Wi-Fi model; TCP itself uses Unix sockets."""

import time

AP_IF = 1
STA_IF = 0
AUTH_OPEN = 0
router = {"up": True, "ssid": "Home", "password": "wifi-secret", "delay_ms": 100}
interfaces = {}
device_hostname = ""


def hostname(value):
    global device_hostname
    device_hostname = value


class WLAN:
    def __new__(cls, mode):
        if mode not in interfaces:
            obj = object.__new__(cls)
            obj.mode = mode
            obj.enabled = False
            obj.started = None
            obj.ssid = ""
            obj.password = ""
            obj.attempts = 0
            obj.ap_starts = 0
            interfaces[mode] = obj
        return interfaces[mode]

    def active(self, value=None):
        if value is not None:
            if value and not self.enabled and self.mode == AP_IF:
                self.ap_starts += 1
            self.enabled = value
            if not value:
                self.started = None
        return self.enabled

    def config(self, key=None, **kwargs):
        if key == "mac":
            return b"\xa2\x20\xa6\x21\xa7\x9c"

    def ifconfig(self):
        return ("192.168.4.1" if self.mode == AP_IF else "192.168.1.20",)

    def disconnect(self):
        self.started = None

    def connect(self, ssid, password):
        self.ssid, self.password = ssid, password
        self.started = time.ticks_ms()
        self.attempts += 1

    def isconnected(self):
        return bool(
            self.enabled
            and self.started is not None
            and router["up"]
            and self.ssid == router["ssid"]
            and self.password == router["password"]
            and time.ticks_diff(time.ticks_ms(), self.started) >= router["delay_ms"]
        )

    def status(self):
        return 3 if self.isconnected() else 1
