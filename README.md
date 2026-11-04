Erase existing firmware and files:
```bash
esptool --chip esp8266 erase-flash
```

Flash MicroPython (replace filename as needed):
```bash
esptool --chip esp8266 --baud 115200 \
  write-flash \
  --flash-mode dout \
  --flash-size detect \
  0x0 firmware/ESP8266_GENERIC-*.bin
```

Deploy the application with `just copy`, then run `just reset`. This compiles
the library modules with `mpy-cross` on the development machine and copies the
small `main.py` plus the HTML pages. Repeat both commands after changes.

On a new device, join the open `RemoteIntercomXXXX` network (the four digits
come from the ESP's MAC address), then browse to `http://192.168.4.1/`.
Log in with the initial password `admin`. The setup page requires a new
administrator password before it saves the home Wi-Fi credentials. A connection
page waits for the result. On success, it shows a final confirmation, then turns
off the provisioning AP after five seconds. If the browser leaves before that
confirmation, the AP turns off within 60 seconds of a successful connection.
Reloading the confirmation never extends that deadline.
On failure, it opens the admin page with the saved SSID ready to edit.

If the home Wi-Fi connection later drops, the AP returns. Log in to reach the
admin page. A new admin password is optional there; leaving the Wi-Fi password
blank keeps the saved password when the SSID is unchanged. Saving settings
starts a new connection attempt when the network changes or is disconnected.
At boot, the device disables any firmware-restored AP and tries the saved
network first, for up to 15 seconds. If that attempt fails, it opens the recovery
AP and continues retrying. With no saved network, the AP opens immediately.
After a later connection drop, the AP returns immediately while reconnecting.
Holding FLASH for password recovery also opens the AP during the boot attempt.
Failed attempts wait 5, 10, 20, 40, then 60 seconds between retries,
continuing at 60 seconds until connected. Each attempt lasts up to 15 seconds.
The recovery AP remains available while disconnected. Saving network settings
while disconnected starts an immediate attempt and resets the backoff.

On the home network, the device requests the same `RemoteIntercomXXXX` name as
its provisioning AP in DHCP. Some routers retain the old `mpy-esp8266` label
until their device list or DHCP lease is refreshed; the station MAC address
does not change.

The HTTP server continues handling AP requests during a retry. The ESP8266
shares one radio between AP and station, so a scan can still briefly interrupt
the phone's connection. After a failed retry the station interface is switched
off until the next attempt.

## Admin-password recovery

The common ESP8266 development-board **FLASH** button is connected to GPIO0.
After the board has booted, hold that button (or connect GPIO0 to GND) for five
seconds to reset only the administrator password to `admin`; saved home Wi-Fi
credentials are retained. The recovery AP is then kept active until the new
password and Wi-Fi setup have been completed again.

Do not hold GPIO0 low while pressing reset or powering on: GPIO0 is a boot-mode
strap and doing so starts the ESP8266 ROM flashing mode rather than the app.

## Serial diagnostics

Attach a 115200-baud serial terminal to the board's USB port before resetting
it. Each HTTP connection gets a number. Its `accepted` and `done` lines show
the time since boot, elapsed milliseconds, response status, bytes sent, free
heap, and whether sending failed. The request line shows the method, path, and
time spent reading headers and body; it never prints passwords or cookies.
Logs are printed to serial only; the device keeps no log history or log file.

An `Alive` line every 30 seconds confirms the main loop is still running.
`Wi-Fi retry start` and `Wi-Fi retry end` bracket a home-network connection
attempt. The server keeps accepting requests during this interval, though
radio scanning can still delay them. `headers too large`,
`request error`, `file error`, and `send error` identify other common reasons
for a page to fail. If a phone attempt produces no `HTTP ... accepted` line,
the request did not reach the Python HTTP handler.

## Provisioning security limitation

The provisioning AP is currently open and the server uses plain HTTP. Someone
nearby capturing wireless traffic can read the submitted administrator password,
home Wi-Fi password and session cookie. Hashing the stored admin password does
not protect these transmissions. HTTP on the home LAN is also unencrypted.

A planned improvement is a unique, randomly generated WPA2 provisioning password
for each device, retained across reboots and supplied through a printed label,
QR code or USB serial during installation. This would protect the provisioning
radio link; home-LAN HTTP would still require separate protection. This security
change is documented only and has not been implemented.

## Request scheduling and validation

The server uses `uasyncio.start_server` and async streams, with at most two
active HTTP requests; excess connections are closed immediately. Wi-Fi
maintenance and reset-button checks run in a separate coroutine every 20 ms.
Each handler has one 10-second `uasyncio.wait_for_ms` budget covering request
reading and response sending; partial progress does not renew it. Cancellation
closes the stream and releases its connection slot. Pending settings changes
restart the radio after the settings request closes, without waiting for other
clients. Flash
writes and Wi-Fi driver calls remain synchronous, and radio scans can briefly
interrupt AP traffic. Password recovery keeps the AP open until setup completes.

Run `just sim-test 64K` for MicroPython integration checks of provisioning,
retry backoff, AP shutdown, concurrent requests, connection limits and recovery.
This Unix-port run uses more heap than the ESP8266 and cannot validate radio
behavior or board heap headroom. Before deployment, test on the ESP8266 with a
browser closed during provisioning, a router outage lasting several retries,
router restoration, and a held FLASH button during a stalled request.

## MicroPython Unix simulator

The simulator runs the compiled application under the `micropython` executable
in PATH, with a configurable GC heap. It uses real MicroPython asyncio, hashing,
configuration files, templates and localhost TCP sockets. Only `network.WLAN`
and the FLASH button (`machine.Pin`) are simulated. The HTTP listener is bound
to `127.0.0.1` on a dynamically selected port. Production still binds to
`0.0.0.0:80`.

Prerequisites: `micropython`, `mpy-cross`, and host `python` in PATH (provided by
the development shell). No third-party host Python packages are required.

```bash
just sim-test          # attempts exact 38 KiB ESP8266 GC heap
just sim-test 64K      # functional Unix-host run (larger heap)
just sim 64K           # interactive browser session
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
