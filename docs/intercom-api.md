# Intercom interface

The `DOOR_RELAY_PIN` and `DOORBELL_PIN` constants near the top of
`src/lib/server.py` select the pins; their defaults are GPIO4 and GPIO5.
Change these constants before building and deploying if the wiring differs.

GPIO4 is an active-low relay output, initialized high. After setup, send
`POST /open` to pulse GPIO4 low for one second; no login is required. The
response is `204 No Content` when accepted,
`429 Too Many Requests` during the five-second cooldown measured from the
accepted request, or `403 Forbidden` if setup is incomplete. Other methods on
`/open` return `405 Method Not Allowed`. Anyone able to reach the device can
open the door.

GPIO5 is an input with its internal pull-up enabled. Connect the doorbell
contact between GPIO5 and ground. A low level stable for 50 ms triggers three
UDP broadcasts containing the bytes `doorbell` to `255.255.255.255:31941`,
200 ms apart. A held contact triggers once; release and press it again for
another notification. UDP delivery is not guaranteed, and listeners need to
be on a network that receives the device's broadcasts.

The application initializes GPIO4 high, but cannot control its state before the
application starts or during reset. The relay circuit must keep the relay off
throughout power-up and reset; verify this on the actual hardware before
connecting the door. Relay and button timing
depend on the device's cooperative event loop and can be delayed by synchronous
flash or Wi-Fi operations.

