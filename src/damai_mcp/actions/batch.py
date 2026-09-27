"""Batch ADB input — send multiple commands in a single adb shell call.

Each ``adb shell`` round-trip costs 30-80ms depending on USB / TCP transport.
When the grab pipeline needs to fire several taps in a row, joining them
into one adb shell command saves ~70% of that overhead.

Two flavours:

* :func:`batch_tap` — taps N points sequentially.
* :func:`batch_send` — raw script of ``input ...`` commands.

These bypass the :func:`damai_mcp.actions.actions.tap` wrapper on purpose —
that wrapper is meant for one-off clicks; batch is the fast path.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..device.adb import adb


async def batch_tap(
    device_id: str,
    points: Sequence[tuple[int, int]],
    *,
    delay_ms: int = 0,
    timeout: float = 10.0,
) -> None:
    """Tap each ``(x, y)`` in order, in one adb shell call.

    Args:
        device_id: target device serial.
        points: list of (x, y) coordinates.
        delay_ms: optional sleep between each tap (ms).
        timeout: total timeout for the single shell call.

    Each tap is dispatched as ``input tap x y`` and chained with ``;``.
    With 5 taps and no delay, this reduces 5×~50ms = 250ms to ~70ms.
    """
    if not points:
        return

    script_parts: list[str] = []
    for x, y in points:
        script_parts.append(f"input tap {int(x)} {int(y)};")
    if delay_ms > 0:
        # Reorder: insert sleeps only between real taps
        spaced: list[str] = []
        for i, part in enumerate(script_parts):
            spaced.append(part)
            if i < len(script_parts) - 1:
                spaced.append(f"sleep {delay_ms / 1000:.3f};")
        script = " ".join(spaced)
    else:
        script = " ".join(script_parts)

    await adb("shell", script, device_id=device_id, timeout=timeout, check=True)


async def batch_swipe(
    device_id: str,
    swipes: Sequence[tuple[int, int, int, int, int]],
    *,
    timeout: float = 10.0,
) -> None:
    """Each item is ``(x1, y1, x2, y2, duration_ms)``.

    All swipes fire in one adb shell. Useful for "swipe up × 5 to scroll to
    bottom" type macros.
    """
    if not swipes:
        return
    script = " ".join(
        f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(d)};"
        for x1, y1, x2, y2, d in swipes
    )
    await adb("shell", script, device_id=device_id, timeout=timeout, check=True)


async def batch_send(
    device_id: str,
    script: str,
    *,
    timeout: float = 10.0,
) -> None:
    """Send a raw adb shell script. Caller is responsible for formatting.

    Example::

        await batch_send(device_id, "input tap 100 200; input tap 300 400;")
    """
    await adb("shell", script, device_id=device_id, timeout=timeout, check=True)
