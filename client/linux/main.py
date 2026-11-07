import http.client
import logging
import socket
import subprocess
import threading
import time
from os import getenv
from typing import Final, NoReturn

DOORBELL_SOUND_PATH: Final[str] = getenv("DOORBELL_SOUND_PATH", "")
ICON_PATH: Final[str] = getenv("ICON_PATH", "")
LISTENING_PORT: Final[int] = int(getenv("LISTENING_PORT", "31941"))
NOTIFICATION_TIMEOUT_S: Final[int] = int(getenv("NOTIFICATION_TIMEOUT_S", "10"))

logger = logging.getLogger(__name__)
notification_lock = threading.Lock()


def notify(sender_ip: str) -> None:
    if not notification_lock.acquire(blocking=False):
        logger.debug("Ignoring doorbell: notification already active")
        return

    try:
        logger.info("Displaying doorbell notification from %s", sender_ip)

        with subprocess.Popen(
            [
                "notify-send",
                "--app-name=Remote Intercom",
                "--urgency=critical",
                "--action=open=Open door",
                "--icon={}".format(ICON_PATH),
                "--hint=string:sound-file:{}".format(DOORBELL_SOUND_PATH),
                # The following two have no effect (due to urgency), but communicate intent
                # in case a notification manager accommodates it.
                "--transient",
                "--expire-time={}".format(NOTIFICATION_TIMEOUT_S * 1000),
                "Doorbell",
                "The doorbell has been rung.",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            try:
                stdout, stderr = proc.communicate(timeout=NOTIFICATION_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                logger.info("Doorbell notification timed out")
                proc.terminate()
                try:
                    stdout, stderr = proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                logger.error(
                    "Doorbell notification failed (exit code %s): %s",
                    proc.returncode,
                    stderr.strip(),
                )
                return

            if stdout.strip() == "open":
                logger.info("Door opening requested for %s", sender_ip)

                connection = http.client.HTTPConnection(sender_ip, timeout=5)
                try:
                    connection.request("POST", "/open")
                    response = connection.getresponse()
                    response.read()

                    if 200 <= response.status < 300:
                        logger.info("Door opening request succeeded for %s", sender_ip)
                    else:
                        logger.error("Door request failed: HTTP %s", response.status)
                except (OSError, http.client.HTTPException):
                    logger.exception("Door request failed")
                finally:
                    connection.close()
            else:
                logger.info("Doorbell notification dismissed without opening door")

    except OSError:
        logger.exception("Failed to launch doorbell notification")
    finally:
        notification_lock.release()


def main() -> NoReturn:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("", LISTENING_PORT))
        logger.info("Listening for doorbell datagrams on UDP port %s", LISTENING_PORT)

        next_notification = 0.0
        while True:
            _, (sender_ip, _) = listener.recvfrom(65535)
            now = time.monotonic()

            if now < next_notification:
                logger.debug("Ignoring doorbell from %s: rate limited", sender_ip)
                continue

            next_notification = now + 1.0
            threading.Thread(
                target=notify,
                args=(sender_ip,),
                name="doorbell-notification",
                daemon=True,
            ).start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down doorbell listener")
