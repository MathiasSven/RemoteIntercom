"""Runs inside MicroPython, from an isolated deployment directory."""

import sys

sys.path[:] = ["", "lib", "sim", ".frozen"]

import gc
import os

import machine
import network
import uasyncio as asyncio
import ujson as json

with open("sim-options.json") as handle:
    options = json.load(handle)
network.router.update(options["router"])

import server

server.HTTP_HOST = "127.0.0.1"
server.HTTP_PORT = options["port"]
if options["fast"]:
    # Only durations change. Tick arithmetic, networking and the scheduler are real.
    server.CONNECT_TIMEOUT_MS = 600
    server.RETRY_INITIAL_MS = 100
    server.RETRY_MAX_MS = 400
    server.SUCCESS_GRACE_MS = 150
    server.SUCCESS_MAX_GRACE_MS = 1000
    server.REQUEST_TIMEOUT_MS = 700
    server.ADMIN_RESET_HOLD_MS = 200

app = server.IntercomServer()
gc.collect()
startup_free = gc.mem_free()
minimum_free = startup_free
sequence = -1


async def controls():
    global sequence, minimum_free
    while True:
        with open("sim-control.json") as handle:  # noqa: ASYNC230 - MicroPython filesystem
            command = json.load(handle)
        if command["sequence"] != sequence:
            network.router.update(command.get("router", {}))
            machine.pressed = command.get("button", False)
            sequence = command["sequence"]
        minimum_free = min(minimum_free, gc.mem_free())
        gc.collect()
        state = {
            "sequence": sequence,
            "ap": app.ap.active(),
            "ap_starts": app.ap.ap_starts,
            "connected": app.sta.isconnected(),
            "attempts": app.sta.attempts,
            "boot_connecting": app.boot_connecting,
            "provisioning": app.provisioning,
            "result": app.connection_result,
            "clients": app.active_clients,
            "must_change_password": app.config["must_change_password"],
            "reset_latched": app.reset_latched,
            "free": gc.mem_free(),
            "startup_free": startup_free,
            "minimum_sampled_free": minimum_free,
        }
        with open("sim-state.json.new", "w") as handle:  # noqa: ASYNC230 - MicroPython filesystem
            json.dump(state, handle)
        os.rename("sim-state.json.new", "sim-state.json")
        await asyncio.sleep_ms(100)


async def main():
    task = asyncio.create_task(controls())
    print(
        "SIM MicroPython", sys.version, "mpy", sys.implementation._mpy, "startup free", startup_free
    )
    try:
        await app.run_async()
    finally:
        task.cancel()


asyncio.run(main())
