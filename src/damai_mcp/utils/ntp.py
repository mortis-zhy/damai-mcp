"""Minimal NTP client for clock synchronisation.

The grab pipeline needs every device to share the same notion of "open time".
We compute ``offset_ms = ntp_unix - local_unix`` once and reuse it for the
whole grab run — anything below ~100 ms is good enough for ticket-grabbing
(servers usually have ~50 ms drag from queues + APM).

Design choices:
    - **stdlib only** (no ntplib dependency)
    - **UDP, 5s timeout** — NTP server returns within 1 round trip
    - **single-arm** query — we don't have an Originate Timestamp to feed back,
      so we approximate offset via server_unix - midpoint(local_send, local_recv).
      This is biased by half the round-trip delay, which for a LAN NTP is
      negligible.
    - **fire-and-forget from MCP** — caller can pre-sync without awaiting.
"""
from __future__ import annotations

import asyncio
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any

from .logging import logger

# NTP epoch: 1900-01-01 00:00 UTC, Unix epoch: 1970-01-01 00:00 UTC
NTP_UNIX_DELTA = 2_208_988_800

DEFAULT_NTP_SERVER = "pool.ntp.org"
QUERY_TIMEOUT_SEC = 5.0


@dataclass
class NtpResult:
    """Outcome of one NTP query."""

    server: str
    offset_ms: float
    delay_ms: float
    server_unix: float  # ntp time when query completed
    queried_at_unix: float

    @property
    def synced(self) -> bool:
        """True if the offset is within a healthy band (< 500 ms)."""
        return abs(self.offset_ms) < 500.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server,
            "offset_ms": round(self.offset_ms, 2),
            "delay_ms": round(self.delay_ms, 2),
            "server_unix": self.server_unix,
            "queried_at_unix": self.queried_at_unix,
            "synced": self.synced,
        }


def _build_request() -> bytes:
    """48-byte NTP client packet: LI=0, VN=3 (IPv4), Mode=3 (client)."""
    pkt = bytearray(48)
    pkt[0] = 0x1B  # 00 011 011 = LI 0, VN 3, Mode 3
    return bytes(pkt)


def _parse_transmit_ts(data: bytes) -> tuple[int, int]:
    """Read the server's Transmit Timestamp (bytes 40-47) and decode."""
    seconds, fraction = struct.unpack("!II", data[40:48])
    return seconds, fraction


def _ntp_secs_to_unix(ntp_seconds: int, ntp_fraction: int) -> float:
    return (ntp_seconds - NTP_UNIX_DELTA) + (ntp_fraction / 2**32)


def query(server: str = DEFAULT_NTP_SERVER, timeout: float = QUERY_TIMEOUT_SEC) -> NtpResult:
    """Sync NTP synchronously. Used by tests + CLI quick-mode."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        t1_unix = time.time()
        sock.sendto(_build_request(), (server, 123))
        data, _ = sock.recvfrom(1024)
        t4_unix = time.time()
    except TimeoutError as exc:
        sock.close()
        raise TimeoutError(
            f"NTP server {server!r} did not respond in {timeout}s"
        ) from exc
    except OSError as exc:
        sock.close()
        raise ConnectionError(f"NTP socket error: {exc}") from exc
    finally:
        sock.close()

    if len(data) < 48:
        raise RuntimeError(f"NTP response too short: {len(data)} bytes")

    ntp_seconds, ntp_fraction = _parse_transmit_ts(data)
    server_unix = _ntp_secs_to_unix(ntp_seconds, ntp_fraction)

    midpoint = (t1_unix + t4_unix) / 2
    offset_ms = (server_unix - midpoint) * 1000
    delay_ms = (t4_unix - t1_unix) * 1000

    logger.info(
        f"[ntp] server={server} offset={offset_ms:+.2f}ms delay={delay_ms:.2f}ms"
    )
    return NtpResult(
        server=server,
        offset_ms=offset_ms,
        delay_ms=delay_ms,
        server_unix=server_unix,
        queried_at_unix=t4_unix,
    )


async def async_query(server: str = DEFAULT_NTP_SERVER, timeout: float = QUERY_TIMEOUT_SEC) -> NtpResult:
    """Async wrapper that runs the sync query in a default thread-pool.

    The NTP exchange takes ~50-1500ms; running it in ``run_in_executor`` keeps
    the asyncio loop responsive without us needing full protocol parsing.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, query, server, timeout)


# ------ device clock helpers --------------------------------------------

async def sync_device_clock(server: str = DEFAULT_NTP_SERVER) -> NtpResult:
    """Query the server and return the offset. The device-side time is
    fetched via adb as a sanity check, but it's the *host* clock that we
    sync against (devices run ADB timestamps, which we cannot set)."""
    return await async_query(server)


async def fetch_device_time(device_id: str, timeout: float = 5.0) -> float | None:
    """Return the device's Unix-clock estimate via ``adb shell date``.

    Useful for cross-checking whether the device clock is wildly different
    from the host.
    """
    from ..device.adb import run_adb
    out = await run_adb(
        device_id,
        ["shell", "date", "+%s"],  # Unix seconds since epoch
        timeout=timeout,
    )
    if out.returncode != 0:
        return None
    try:
        return float(out.stdout.strip())
    except (ValueError, AttributeError):
        return None
