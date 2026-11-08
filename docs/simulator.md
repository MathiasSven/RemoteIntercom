# MicroPython Unix simulator

The simulator runs the compiled application under the `micropython` executable
in PATH, with a configurable GC heap. It uses real MicroPython asyncio, hashing,
configuration files, templates and localhost TCP sockets. `network.WLAN` and
GPIO pins (`machine.Pin`) are simulated. Doorbell datagrams use localhost, so
the simulator does not verify broadcast delivery. The HTTP listener is bound
to `127.0.0.1` on a dynamically selected port. Production still binds to
`0.0.0.0:80`.

Prerequisites: `micropython`, `mpy-cross`, and host `python` in PATH (provided by
the development shell). No third-party host Python packages are required.

```bash
just sim-test          # functional Unix-host run at 64 KiB
just sim-test 38K      # attempts exact 38 KiB ESP8266 GC heap
just sim               # interactive browser session at 64 KiB
```

Equivalent direct command: `python tests/simulate.py test --heap 64K --repeat 50`.
The actual ESP8266 MicroPython 1.29 heap is 38 KiB. On the installed Unix
MicroPython 1.27 runtime, the app cannot be imported within 38 KiB: it raises
`MemoryError` while loading `server.mpy`. The simulator can run the full test
suite at 64 KiB, but that run is not a board heap equivalent.
The runner compiles both application and simulator helpers into a temporary
folder, starts MicroPython there, and removes it on exit. It does not read or
modify device credentials, repository config files, or `dist`. Failed tests
print the simulator serial log and exit nonzero, including on `MemoryError`.
Tests require permission to open localhost sockets when run in a sandbox.

The interactive command prints a browser URL and temporary directory. Log in
with `admin`, then set a new admin password and provision mock Wi-Fi `Home` with
password `wifi-secret`. The mock network controls do not configure host Wi-Fi;
HTTP remains accessible on localhost even when the simulated AP is off.

The temporary directory contains:

- `serial.log`: application logs and MicroPython tracebacks.
- `sim-state.json`: AP/station state, attempt count, client count and heap samples.
- `sim-control.json`: router/button controls; increment `sequence` for each update.

For example, write this to `sim-control.json.new` and atomically rename it over
`sim-control.json` to simulate a router outage:

```json
{"sequence": 1, "router": {"up": false}, "button": false}
```

Use `{"sequence": 2, "router": {"up": true}, "button": true}` to restore the
router and hold FLASH; release it with a later update containing `"button": false`.
Router controls also accept `ssid`, `password`, and `delay_ms`. Router settings
persist across control updates; an omitted `button` means released.

Automated tests accelerate timeout constants, retaining real tick arithmetic
and scheduler behavior. They exercise station-first boot, failed boot fallback,
login, settings persistence, browser-independent AP shutdown, repeated page
requests, concurrent clients, connection limits, stalled/trickling requests,
physical password recovery and router outage/reconnection.

Memory results describe this Unix runtime, not an exact ESP8266 memory budget.
The simulator itself consumes heap and samples/collects garbage every 100 ms;
`minimum_sampled_free` is not an exact allocation high-water mark. Desktop object
sizes, frozen modules, socket buffers and Wi-Fi driver allocations differ from
the board. Local HTTP also does not reproduce radio contention or packet loss.
The 38 KiB value comes from the ESP8266 heap declaration in the MicroPython
1.29 source. The installed Unix runtime is 1.27.0; `mpy-cross` emits 1.29.0
bytecode. Although the 1.27 runtime accepts the bytecode at a larger heap, its
Unix port uses more of the GC heap before application import than the ESP8266
port does. Therefore, the exact 38 KiB run currently detects this runtime
limit; it cannot serve requests. Use the 64 KiB run for protocol and state
flow checks only. A true 38 KiB end-to-end run needs an ESP8266-target emulator
with working mockable networking, or a Unix MicroPython build with a lower
startup heap footprint.
