# Design notes

## Provisioning security limitation

The provisioning AP is open and the server uses plain HTTP. During setup and
settings changes, submitted passwords can be read by someone capturing the
traffic. Administrator logins and session cookies are also sent unencrypted,
including on the home LAN. Hashing the stored admin password does not protect
these transmissions.

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

