# Operation and troubleshooting

## Wi-Fi recovery

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
At startup, `Intercom relay GPIO` reports the selected pins, the initialized
relay state and the initial doorbell level. A debounced transition logs `Doorbell GPIO`
and the station connection state. Each successful UDP send logs `Doorbell UDP
sent`; `Doorbell broadcast error` reports the failed socket operation and error.
A successful send
means the local network stack accepted the packet, not that a listener received
it. If GPIO5 stays low from startup, release it and press again to trigger a
new event.
`Wi-Fi retry start` and `Wi-Fi retry end` bracket a home-network connection
attempt. The server keeps accepting requests during this interval, though
radio scanning can still delay them. `headers too large`,
`request error`, `file error`, and `send error` identify other common reasons
for a page to fail. If a phone attempt produces no `HTTP ... accepted` line,
the request did not reach the Python HTTP handler.

