"""Caching layer over :mod:`damai_mcp.inspector.dump`.

Background:
    Each :func:`find_by_text` / :func:`wait_for_element` call invokes
    ``uiautomator dump``, which costs ~250-350ms on a real device. When the
    grab pipeline fires 5 finds in a row on the same page (very common —
    ``buy → price tier → viewer → confirm → submit``), we waste 5× the time.

Strategy:
    Take a tiny screenshot (or just the screencap header) and hash it.
    If the hash matches the cached one AND the cache is fresh (TTL),
    return cached :class:`UIElement` list. Otherwise re-dump.

TTL defaults to 1.0s which is conservative for sub-second scrapes; bump
lower (0.2s) for hot loops.
"""
from __future__ import annotations

import asyncio
import hashlib
import time

from ..device.adb import adb
from ..inspector.dump import dump_ui
from ..inspector.models import UIElement

DEFAULT_TTL_SEC = 1.0
SCREENCAP_HEADER_BYTES = 4096  # cheap fingerprint without the whole PNG


class UICache:
    """Per-device screen-state cache.

    Two devices share state independently; one cache instance per device.
    """

    def __init__(self, ttl_sec: float = DEFAULT_TTL_SEC) -> None:
        self._ttl = ttl_sec
        self._screen_hash: str | None = None
        self._fetched_at: float = 0.0
        self._elements: list[UIElement] = []
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    @property
    def stats(self) -> dict[str, int]:
        """Snapshot of cache hit/miss counts (for telemetry)."""
        return {"hits": self._hits, "misses": self._misses}

    def invalidate(self) -> None:
        """Force the next :meth:`get` to re-dump."""
        self._screen_hash = None
        self._fetched_at = 0.0

    async def _fingerprint(self, device_id: str) -> str | None:
        """Hash a small screencap to detect screen changes cheaply."""
        try:
            result = await adb(
                "exec-out", "screencap", "-p",
                device_id=device_id, timeout=3.0, check=False,
            )
        except Exception:
            return None
        if not result.ok or not result.stdout_bytes:
            return None
        # Use just the first N bytes — PNG header is stable per layout,
        # pixel-perfect comparison is not needed.
        head = result.stdout_bytes[:SCREENCAP_HEADER_BYTES]
        return hashlib.md5(head).hexdigest()

    async def get(self, device_id: str) -> list[UIElement]:
        """Return cached elements if the screen hasn't changed.

        Concurrent calls share a single underlying dump via an asyncio.Lock.
        """
        async with self._lock:
            now = time.monotonic()
            age = now - self._fetched_at
            if self._screen_hash is not None and age < self._ttl:
                h = await self._fingerprint(device_id)
                if h is not None and h == self._screen_hash:
                    self._hits += 1
                    return self._elements
            self._misses += 1
            self._elements = await dump_ui(device_id)
            self._screen_hash = await self._fingerprint(device_id)
            self._fetched_at = time.monotonic()
            return self._elements

    async def find(
        self,
        device_id: str,
        *,
        text: str | None = None,
        resource_id: str | None = None,
        xpath: str | None = None,
        exact: bool = True,
    ) -> UIElement | None:
        """Cached wrapper — like ``find_by_text`` but skips dump if possible."""
        from .find_helpers import search_elements
        elements = await self.get(device_id)
        return search_elements(elements, text=text, resource_id=resource_id,
                                xpath=xpath, exact=exact)
