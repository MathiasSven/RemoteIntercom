"""Bounded HTTP stream output and form decoding for MicroPython."""

import gc
import os

import uasyncio as asyncio

TEMPLATE_DIR = "www"
PAGE_CHUNK_BYTES = 32


def hex_digit(value: int) -> int:
    if 48 <= value <= 57:
        return value - 48
    if 65 <= value <= 70:
        return value - 55
    if 97 <= value <= 102:
        return value - 87
    return -1


def form_decode(value: bytes, start: int, end: int) -> str:
    result = bytearray(end - start)
    output = 0
    index = start
    while index < end:
        character = value[index]
        if character == 43:  # +
            result[output] = 32
            output += 1
        elif character == 37 and index + 2 < end:  # %xx
            high = hex_digit(value[index + 1])
            low = hex_digit(value[index + 2])
            if high >= 0 and low >= 0:
                decoded = high * 16 + low
                index += 2
            else:
                decoded = 37
            result[output] = decoded
            output += 1
        else:
            result[output] = character
            output += 1
        index += 1
    try:
        return result[:output].decode("utf-8")
    except UnicodeError:
        return ""


def parse_form(body: bytes) -> dict[str, str]:
    values = {}
    start = 0
    while start < len(body):
        end = body.find(b"&", start)
        if end < 0:
            end = len(body)
        separator = body.find(b"=", start, end)
        if separator >= 0:
            key = form_decode(body, start, separator)
            value = form_decode(body, separator + 1, end)
            values[key] = value
        start = end + 1
    return values


class HTTPClient:
    """Per-request streams and diagnostics, never shared between tasks."""

    def __init__(
        self, reader: "asyncio.StreamReader", writer: "asyncio.StreamWriter", number: int
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.request_count = number
        self.response_status = "-"
        self.bytes_sent = 0
        self.send_failed = False

    async def recv(self, size: int) -> bytes:
        return await self.reader.read(size)

    async def send(self, data: bytes | memoryview) -> int:
        self.writer.write(data)
        await self.writer.drain()
        # drain may complete immediately; yield even for a writable socket.
        await asyncio.sleep_ms(0)
        return len(data)


async def send_bytes(client: HTTPClient, pending: bytes | memoryview) -> bool:
    """Write all bytes without assuming one socket send is sufficient."""
    pending = memoryview(pending)
    try:
        while pending:
            written = await client.send(pending)
            if not written:
                client.send_failed = True
                print("HTTP", client.request_count, "send returned zero, remaining", len(pending))
                return False
            client.bytes_sent += written
            pending = pending[written:]
    except OSError as error:
        client.send_failed = True
        print("HTTP", client.request_count, "send error:", error)
        return False
    return True


async def send_headers(
    client: HTTPClient, status: str, content_length: int, headers: str = ""
) -> bool:
    # HTTP/1.0 closes the connection by default, saving an allocation for
    # Connection: close.  Redirects have no body and need no content type.
    client.response_status = status
    if not await send_bytes(client, ("HTTP/1.0 " + status + "\r\n").encode("utf-8")):
        return False
    if content_length and not await send_bytes(client, b"Content-Type:text/html\r\n"):
        return False
    if not await send_bytes(client, b"Cache-Control:no-store\r\n"):
        return False
    if not await send_bytes(
        client, ("Content-Length:" + str(content_length) + "\r\n").encode("utf-8")
    ):
        return False
    if headers and not await send_bytes(client, headers.encode("utf-8")):
        return False
    return await send_bytes(client, b"\r\n")


async def send(client: HTTPClient, status: str, body: str, headers: str = "") -> None:
    encoded = body.encode("utf-8")
    if await send_headers(client, status, len(encoded), headers) and encoded:
        await send_bytes(client, encoded)


async def send_file(client: HTTPClient, status: str, name: str, headers: str = "") -> bool:
    """Stream a static page from flash; do not load a full template in RAM."""
    filename = TEMPLATE_DIR + "/" + name
    try:
        if not await send_headers(client, status, os.stat(filename)[6], headers):
            return False
        gc.collect()
        with open(filename, "rb") as handle:  # noqa: ASYNC230 - MicroPython flash API is synchronous
            while True:
                chunk = handle.read(PAGE_CHUNK_BYTES)
                if not chunk:
                    return True
                if not await send_bytes(client, chunk):
                    return False
    except OSError as error:
        print("HTTP", client.request_count, "file error", name, error)
        return False
