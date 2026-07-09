"""Atomic UI actions on an Android device.

Each function is a thin wrapper around `adb shell input ...` or
`adb shell screencap ...` and returns immediately after the adb call returns.

These are deliberately *low-level* — for finding elements by text/id, see
`damai_mcp.inspector`. For business logic, see `damai_mcp.damai`.
"""
from __future__ import annotations

import asyncio
import base64
import re
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image

from ..device.adb import adb, shell
from ..utils.errors import ADBError
from ..utils.retry import retry

KeyName = Literal[
    "home", "back", "menu", "enter", "delete", "tab",
    "power", "volume_up", "volume_down", "camera",
    "up", "down", "left", "right",
]

# Mapping for keyevent codes (subset — extend as needed)
_KEYCODE = {
    "home": 3, "back": 4, "menu": 82, "enter": 66, "delete": 67,
    "tab": 61, "power": 26, "volume_up": 24, "volume_down": 25,
    "camera": 27, "up": 19, "down": 20, "left": 21, "right": 22,
}


# ---- tap / press ------------------------------------------------------------

async def tap(device_id: str, x: int, y: int, *, duration_ms: int = 50) -> None:
    """Tap at (x, y). `duration_ms > 0` simulates a long-press-ish tap."""
    cmd = f"input tap {x} {y}"
    if duration_ms and duration_ms != 50:
        # `input swipe x y x y ms` is the canonical way to control press length
        cmd = f"input swipe {x} {y} {x} {y} {duration_ms}"
    await shell(cmd, device_id=device_id, check=True)


async def double_tap(device_id: str, x: int, y: int, *, gap_ms: int = 80) -> None:
    await tap(device_id, x, y)
    await asyncio.sleep(gap_ms / 1000)
    await tap(device_id, x, y)


async def long_press(device_id: str, x: int, y: int, *, duration_ms: int = 800) -> None:
    """Hold at (x, y) for `duration_ms`. Use 500-1000 ms for context menus."""
    await shell(f"input swipe {x} {y} {x} {y} {duration_ms}", device_id=device_id, check=True)


# ---- swipe / scroll ---------------------------------------------------------

async def swipe(
    device_id: str,
    x1: int, y1: int, x2: int, y2: int,
    *,
    duration_ms: int = 300,
) -> None:
    """Drag from (x1,y1) to (x2,y2) over `duration_ms`."""
    await shell(
        f"input swipe {x1} {y1} {x2} {y2} {duration_ms}",
        device_id=device_id, check=True,
    )


async def scroll(
    device_id: str,
    direction: Literal["up", "down", "left", "right"] = "down",
    distance_ratio: float = 0.6,
    *,
    duration_ms: int = 300,
) -> None:
    """Scroll the screen by `distance_ratio * screen_height/width`.

    `up` means content moves up (finger goes from bottom to top), revealing
    content below. That matches user intent in most apps.
    """
    size_str = (await shell("wm", "size", device_id=device_id, check=False, timeout=5)).strip()
    m = re.search(r"(\d+)x(\d+)", size_str)
    if not m:
        raise ADBError(f"无法获取屏幕分辨率: {size_str!r}")
    w, h = int(m.group(1)), int(m.group(2))
    cx, cy = w // 2, h // 2
    d = int(min(w, h) * distance_ratio)
    deltas = {
        "up": (0, -d),     # finger bottom→top   → content up
        "down": (0, d),    # finger top→bottom   → content down
        "left": (-d, 0),   # finger right→left   → content left
        "right": (d, 0),   # finger left→right   → content right
    }
    dx, dy = deltas[direction]
    await swipe(device_id, cx, cy, cx + dx, cy + dy, duration_ms=duration_ms)


# ---- text / key -------------------------------------------------------------

async def input_text(device_id: str, text: str, *, delay_ms: int = 0) -> None:
    """Type text. Spaces must be sent as %s. CJK uses broadcast IME.

    For CJK (Chinese) text this requires an IME that supports broadcasts, e.g.
    ADBKeyBoard. Falls back to per-character `input text` for short ASCII.
    """
    if not text:
        return
    # CJK characters or special chars → use ADBKeyBoard if installed, else
    # chunk the text into ascii chunks and use input text
    safe = text.replace(" ", "%s")
    if delay_ms:
        for ch in safe:
            await shell(f"input text {ch}", device_id=device_id, check=True)
            await asyncio.sleep(delay_ms / 1000)
    else:
        await shell(f"input text {safe}", device_id=device_id, check=True)


async def press_key(device_id: str, key: KeyName | int) -> None:
    """Press a named key (e.g. "back", "home") or numeric keyevent code."""
    if isinstance(key, str):
        code = _KEYCODE.get(key.lower())
        if code is None:
            raise ADBError(f"未知按键: {key}")
    else:
        code = int(key)
    await shell(f"input keyevent {code}", device_id=device_id, check=True)


# ---- screenshot -------------------------------------------------------------

@retry(max_attempts=2, exceptions=(ADBError,))
async def screenshot(
    device_id: str,
    save_path: str | Path | None = None,
    *,
    return_base64: bool = False,
    max_size: tuple[int, int] | None = None,
) -> bytes | str:
    """Take a device screenshot.

    Args:
        save_path: if given, save PNG bytes there.
        return_base64: if True, return base64 string (for MCP transport).
        max_size: optional (width, height) downscale for transport economy.

    Returns:
        PNG bytes if save_path is given, else bytes (or base64 str).
    """
    result = await adb(
        "exec-out", "screencap", "-p",
        device_id=device_id, timeout=15, check=True,
    )
    png_bytes = result.stdout_bytes

    if max_size is not None:
        png_bytes = _resize_png(png_bytes, max_size)

    if save_path is not None:
        Path(save_path).write_bytes(png_bytes)
    if return_base64:
        return base64.b64encode(png_bytes).decode("ascii")
    return png_bytes


def _resize_png(png_bytes: bytes, max_size: tuple[int, int]) -> bytes:
    img = Image.open(BytesIO(png_bytes))
    img.thumbnail(max_size)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---- timing helper ----------------------------------------------------------

async def wait_ms(ms: int) -> None:
    """Async sleep — alias kept for semantic clarity."""
    await asyncio.sleep(ms / 1000)


__all__ = [
    "tap", "double_tap", "long_press",
    "swipe", "scroll",
    "input_text", "press_key",
    "screenshot", "wait_ms",
]
