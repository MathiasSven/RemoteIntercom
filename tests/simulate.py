"""Build isolated .mpy deployments and exercise them over real HTTP."""

import argparse
import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def compile_modules(destination):
    for source in sorted((ROOT / "src/lib").glob("*.py")):
        subprocess.run(
            ["mpy-cross", "-o", str(destination / "lib" / (source.stem + ".mpy")), str(source)],
            check=True,
        )
    for source in sorted((ROOT / "tests/simulator").glob("*.py")):
        subprocess.run(
            ["mpy-cross", "-o", str(destination / "sim" / (source.stem + ".mpy")), str(source)],
            check=True,
        )


class Simulation:
    def __init__(self, heap, saved=False, router_up=True, fast=True, router_ssid="Home"):
        self.temporary = tempfile.TemporaryDirectory(prefix="intercom-sim-")
        self.path = Path(self.temporary.name)
        self.process = None
        self.log = None
        try:
            (self.path / "lib").mkdir()
            (self.path / "sim").mkdir()
            compile_modules(self.path)
            shutil.copytree(ROOT / "src/www", self.path / "www")
            # Use a tiny loader just as deployment does, avoiding source compilation.
            (self.path / "main.py").write_text(
                'import sys\nsys.path.insert(0, "sim")\nimport boot\n'
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                self.port = sock.getsockname()[1]
            self.sequence = 0
            write_json(
                self.path / "sim-options.json",
                {
                    "port": self.port,
                    "fast": fast,
                    "router": {
                        "up": router_up,
                        "ssid": router_ssid,
                        "password": "wifi-secret",
                        "delay_ms": 100,
                    },
                },
            )
            write_json(self.path / "sim-control.json", {"sequence": 0})
            if saved:
                write_json(
                    self.path / "intercom-config.json",
                    {
                        "password_salt": "sim-salt",
                        "password_hash": hashlib.sha256(b"sim-salt:admin-secret").hexdigest(),
                        "must_change_password": False,
                        "wifi_ssid": "Home",
                        "wifi_password": "wifi-secret",
                    },
                )
            self.log = (self.path / "serial.log").open("w+")
            self.process = subprocess.Popen(
                ["micropython", "-X", "heapsize=" + heap, "main.py"],
                cwd=self.path,
                stdout=self.log,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, MICROPYPATH=""),
            )
            self.wait(lambda s: True)
        except BaseException:
            self.close(failed=True)
            raise

    def state(self):
        if self.process.poll() is not None:
            raise RuntimeError("MicroPython exited with " + str(self.process.returncode))
        try:
            return json.loads((self.path / "sim-state.json").read_text())
        except FileNotFoundError:
            return None

    def wait(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = self.state()
            if last is not None and predicate(last):
                return last
            time.sleep(0.02)
        raise AssertionError("state timed out: " + repr(last))

    def control(self, **changes):
        self.sequence += 1
        write_json(self.path / "sim-control.json", dict(changes, sequence=self.sequence))
        return self.wait(lambda s: s["sequence"] == self.sequence)

    def request(self, path="/", data=None, cookie=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Cookie": cookie} if cookie else {}
        body = urlencode(data) if data is not None else None
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            connection.request("POST" if body is not None else "GET", path, body, headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def login(self, password):
        status, headers, _ = self.request("/login", {"password": password})
        assert status == 303, status
        return headers["Set-Cookie"].split(";", 1)[0]

    def close(self, failed=False):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.log is not None:
            self.log.close()
        if failed:
            print("--- simulator serial output ---")
            log = self.path / "serial.log"
            if log.exists():
                print(log.read_text())
        self.temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.close(failed=kind is not None)


def check(heap, repeat):
    with Simulation(heap, router_ssid="SimNet-42") as sim:
        assert sim.wait(lambda s: s["ap"])["attempts"] == 0
        assert b"Remote Intercom login" in sim.request()[2]
        status, headers, _ = sim.request("/login", {"password": "wrong"})
        assert status == 303 and "Set-Cookie" not in headers
        cookie = sim.login("admin")
        status, headers, _ = sim.request(
            "/setup",
            {
                "admin_password": "admin-secret",
                "ssid": "SimNet-42",
                "wifi_password": "wifi-secret",
            },
            cookie,
        )
        assert status == 303 and headers["Location"] == "/connecting"
        persisted = json.loads((sim.path / "intercom-config.json").read_text())
        assert persisted["wifi_ssid"] == "SimNet-42" and not persisted["must_change_password"]
        expected = hashlib.sha256(
            (persisted["password_salt"] + ":admin-secret").encode()
        ).hexdigest()
        assert persisted["password_hash"] == expected
        # No success-page fetch: AP must shut down autonomously.
        sim.wait(lambda s: s["connected"] and not s["ap"])
        cookie = sim.login("admin-secret")
        before = sim.wait(lambda s: s["clients"] == 0)["free"]
        for _ in range(repeat):
            status, _, body = sim.request("/admin", cookie=cookie)
            assert status == 200 and b'value="SimNet-42"' in body
        after = sim.wait(lambda s: s["clients"] == 0)["free"]
        # Allow allocator/interning noise; catch retained per-request buffers.
        assert after >= before - 4096, (before, after)
        print(heap, "repeated requests:", repeat, "free before/after:", before, after)

        # Two stalled clients occupy the slots; a third must be closed promptly.
        with (
            socket.create_connection(("127.0.0.1", sim.port), timeout=2) as first,
            socket.create_connection(("127.0.0.1", sim.port), timeout=2) as second,
        ):
            first.sendall(b"GET / HTTP/1.1\r\n")
            second.sendall(b"GET / HTTP/1.1\r\n")
            sim.wait(lambda s: s["clients"] == 2)
            with socket.create_connection(("127.0.0.1", sim.port), timeout=2) as excess:
                assert excess.recv(1) == b""
            assert first.recv(1) == b"" and second.recv(1) == b""
        sim.wait(lambda s: s["clients"] == 0)
        # Partial progress must not renew the absolute request deadline.
        with socket.create_connection(("127.0.0.1", sim.port), timeout=2) as trickle:
            trickle.sendall(b"GET / HTTP/1.1\r\nX-Slow: ")
            for _ in range(4):
                time.sleep(0.1)
                trickle.sendall(b"x")
            assert trickle.recv(1) == b""
        sim.wait(lambda s: s["clients"] == 0)

        # A real partial request must not block another HTTP client or recovery.
        with socket.create_connection(("127.0.0.1", sim.port), timeout=2) as slow:
            slow.sendall(b"GET / HTTP/1.1\r\nX-Slow: ")
            sim.wait(lambda s: s["clients"] == 1)
            assert sim.request("/admin", cookie=cookie)[0] == 200
            sim.control(button=True)
            sim.wait(lambda s: s["reset_latched"])
            assert slow.recv(1) == b""  # request deadline closes the socket
        sim.control(button=False)
        assert sim.wait(lambda s: s["must_change_password"] and s["ap"])
        sim.login("admin")

    with Simulation(heap, saved=True) as sim:
        state = sim.wait(lambda s: s["connected"])
        assert state["ap_starts"] == 0, state
        sim.control(router={"up": False})
        sim.wait(lambda s: s["ap"] and not s["connected"])
        baseline = sim.state()["attempts"]
        sim.wait(lambda s: s["attempts"] >= baseline + 2)
        sim.control(router={"up": True})
        sim.wait(lambda s: s["connected"] and not s["ap"])

    with Simulation(heap, saved=True, router_up=False) as sim:
        state = sim.state()
        assert not state["ap"] and state["boot_connecting"], state
        sim.wait(lambda s: s["ap"] and not s["boot_connecting"])
        print(heap, "PASS; heap sample:", sim.state())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("test", "serve"), nargs="?", default="test")
    parser.add_argument("--heap", default="38K", help="MicroPython GC heap, e.g. 64K")
    parser.add_argument("--repeat", type=int, default=50)
    args = parser.parse_args()
    if args.mode == "test":
        check(args.heap, args.repeat)
    else:
        with Simulation(args.heap, fast=False) as sim:
            print("Browser: http://127.0.0.1:" + str(sim.port), flush=True)
            print("Initial admin password: admin; mock Wi-Fi: Home / wifi-secret", flush=True)
            print("State/control/log files:", sim.path, flush=True)
            print("Ctrl-C stops the simulator and deletes its isolated files.", flush=True)
            try:
                while True:
                    sim.state()
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
