import time
from typing import TYPE_CHECKING

import ubinascii
import uhashlib
import urandom

if TYPE_CHECKING:
    # Opaque tick types exist only in the MicroPython stubs.
    from _mpy_shed.time_mp import _TicksMs


def new_salt() -> str:
    # Avoid CPython-only convenience APIs: getrandbits is present on ESP8266.
    return f"{urandom.getrandbits(32):08x}{urandom.getrandbits(32):08x}"


def password_digest(password: str, salt: str) -> str:
    # SHA-256 is available as uhashlib on current ESP8266 MicroPython builds.
    digest = uhashlib.sha256()
    digest.update(salt.encode("utf-8"))
    digest.update(b":")
    digest.update(password.encode("utf-8"))
    return ubinascii.hexlify(digest.digest()).decode("ascii")


def ticks_expired(now: "_TicksMs", deadline: "_TicksMs") -> bool:
    """Return true when *deadline* has passed, including tick counter wrap."""
    return time.ticks_diff(now, deadline) >= 0
