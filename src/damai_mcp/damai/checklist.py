"""One-shot grab day checklist.

Run a full grab session end-to-end with explicit phases and progress reporting.
This is the killer UX feature: 1 command runs everything from launch to submit.

Phases:
    0. Connectivity check          (device + adb working)
    1. App launch + login verify   (re-login if needed)
    2. Detail page preheat         (open url ahead of time, in cached state)
    3. Countdown loop              (status update every minute)
    4. Open-time trigger           (at T-0 fire the grab pipeline)
    5. Result + optional reminder

The actual clicking happens via :func:`damai_mcp.damai.actions.damai_grab`.
This module owns scheduling, status, and human-readable progress.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..utils.logging import logger

# Imported at module level so they can be monkeypatched in tests.
from .actions import (
    damai_grab,
    damai_login_check,
    damai_open_concert,
)

# Seconds between status pings while waiting for open_time
COUNTDOWN_TICK_SEC = 60

# How many seconds to wait before open_time for the preheat to fully land
DEFAULT_PREHEAT_SECONDS = 30.0


@dataclass
class PhaseEvent:
    """A single checkpoint recorded during the checklist run."""

    phase: str
    started_at_ms: int
    finished_at_ms: int | None = None
    note: str = ""

    @property
    def elapsed_ms(self) -> int:
        if self.finished_at_ms is None:
            return 0
        return self.finished_at_ms - self.started_at_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "started_at_ms": self.started_at_ms,
            "finished_at_ms": self.finished_at_ms,
            "elapsed_ms": self.elapsed_ms,
            "note": self.note,
        }


@dataclass
class ChecklistResult:
    """Full report of a checklist run, json-serializable."""

    status: str  # "submitted" | "needs_human" | "failed" | "expired" | "preheat_open_time"
    phases: list[PhaseEvent] = field(default_factory=list)
    grab_result: dict[str, Any] | None = None
    error: str | None = None
    ntp_offset_ms: float | None = None  # if NTP sync module was used

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "phases": [p.to_dict() for p in self.phases],
            "grab_result": self.grab_result,
            "error": self.error,
            "ntp_offset_ms": self.ntp_offset_ms,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


def parse_open_time(open_time: str) -> datetime | None:
    """Parse 'YYYY-MM-DD HH:MM:SS' or ISO. None if open_time is empty/now."""
    if not open_time or open_time.lower() in ("", "now", "立即"):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(open_time, fmt)
        except ValueError:
            continue
    # ISO with +08:00
    try:
        # Drop tzinfo for simplicity (we use local time)
        return datetime.fromisoformat(open_time.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(
            f"无法解析 open_time='{open_time}', 期望 'YYYY-MM-DD HH:MM:SS'"
        ) from exc


async def _countdown_loop(
    target_unix: float,
    progress_cb: Callable[[float, int], Awaitable[None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Wait until ``target_unix`` epoch seconds.

    Calls ``progress_cb(seconds_left, total_seconds_elapsed)`` every
    :data:`COUNTDOWN_TICK_SEC` seconds (or every second in the last 10
    seconds). Returns early if ``stop_event`` is set.
    """
    started = time.time()
    while True:
        now = time.time()
        left = target_unix - now
        elapsed = now - started
        if left <= 0:
            return
        if stop_event is not None and stop_event.is_set():
            return
        tick = COUNTDOWN_TICK_SEC if left > 10 else 1
        if progress_cb is not None:
            try:
                await progress_cb(left, int(elapsed))
            except Exception:  # never let a bad callback kill the wait
                logger.exception("countdown callback raised, continuing")
        await asyncio.sleep(tick)


async def run_checklist(
    device_id: str,
    item_id: str,
    *,
    open_time: str = "",
    price_index: int = 1,
    viewer_names: list[str] | None = None,
    ticket_num: int = 1,
    preheat_seconds: float = DEFAULT_PREHEAT_SECONDS,
    ntp_server: str = "pool.ntp.org",
    ntp_timeout_sec: float = 5.0,
    on_phase: Callable[[str], Awaitable[None]] | None = None,
    on_progress: Callable[[float, int], Awaitable[None]] | None = None,
) -> ChecklistResult:
    """Run the full grab-day checklist.

    Args:
        device_id: ADB serial.
        item_id: Show item id.
        open_time: 'YYYY-MM-DD HH:MM:SS' or empty for "grab now".
        price_index: 1-based price tier to pick.
        viewer_names: List of viewer names (大麦实名制).
        ticket_num: Number of tickets.
        preheat_seconds: Pre-open lead time for the grab pump.
        ntp_server: NTP server (default pool.ntp.org).
        ntp_timeout_sec: NTP timeout.
        on_phase: Async callback fired when each phase begins.
        on_progress: Async callback fired each countdown tick with (seconds_left, elapsed_s).

    Returns:
        :class:`ChecklistResult` with per-phase timings and final grab outcome.
    """
    result = ChecklistResult(status="preheat_open_time")
    phases: list[PhaseEvent] = result.phases

    def _begin(name: str, note: str = "") -> PhaseEvent:
        ev = PhaseEvent(phase=name, started_at_ms=_now_ms(), note=note)
        phases.append(ev)
        if on_phase is not None:
            asyncio.create_task(_safe_cb(on_phase, name))
        return ev

    def _end(ev: PhaseEvent) -> None:
        ev.finished_at_ms = _now_ms()

    # ---- Phase -1: NTP sync (best effort) ----
    p_ntp = _begin("ntp_sync", f"server={ntp_server}")
    try:
        from ..utils.ntp import async_query
        ntp_res = await async_query(ntp_server, ntp_timeout_sec)
        result.ntp_offset_ms = ntp_res.offset_ms
        logger.info(
            f"[checklist] NTP offset={ntp_res.offset_ms:+.2f}ms delay={ntp_res.delay_ms:.2f}ms"
        )
    except Exception as exc:
        logger.warning(f"[checklist] NTP sync failed (continuing without): {exc}")
    _end(p_ntp)

    parsed = parse_open_time(open_time)
    target_unix = parsed.timestamp() if parsed else None

    # ---- Phase 0: connectivity check ----
    p0 = _begin("connectivity", f"device={device_id}")
    try:
        from ..device.manager import DeviceManager
        info = await DeviceManager.shared().require(device_id)
        logger.info(f"[checklist] device ok: {info.model} {info.screen_size}")
    except Exception as exc:
        _end(p0)
        result.status = "failed"
        result.error = f"device_unreachable: {exc}"
        return result
    _end(p0)

    # ---- Phase 1: app launch + login check ----
    p1 = _begin("login_check")
    try:
        logged_in = await damai_login_check(device_id, timeout=3.0)
        if not logged_in.get("logged_in", False):
            logger.warning("[checklist] not logged in — user needs to login manually")
        result.grab_result = {"login_check": logged_in}
    except Exception as exc:
        logger.warning(f"[checklist] login_check raised: {exc}")
    _end(p1)

    # ---- Phase 2: detail page preheat ----
    # Open the detail page early so the buy button is already cached
    if target_unix is not None and preheat_seconds > 0:
        p2 = _begin("preheat_open", f"preheat_seconds={preheat_seconds}")
        await damai_open_concert(device_id, item_id)
        _end(p2)

        # ---- Phase 2.5: parallel dump warmup ----
        # Spam UI dumps + screenshots in parallel during preheat, so when
        # open-time fires the screen is already "hot" in OS caches and the
        # first find_by_text fires in <50ms instead of ~300ms.
        if preheat_seconds >= 5.0:
            p25 = _begin("preheat_warm_dump", "parallel UI dump × 3")
            try:
                from ..actions.actions import screenshot as _screenshot
                from ..inspector.dump import dump_ui
                await asyncio.gather(
                    dump_ui(device_id),
                    dump_ui(device_id, refresh=True),
                    _screenshot(device_id),
                    return_exceptions=True,
                )
            except Exception as exc:
                logger.warning(f"[checklist] warm-dump failed (non-fatal): {exc}")
            _end(p25)

        # ---- Phase 3: countdown ----
        p3 = _begin("countdown", f"open_time={open_time}")
        fire_at = target_unix - preheat_seconds
        try:
            await _countdown_loop(fire_at, progress_cb=on_progress)
        except asyncio.CancelledError:
            _end(p3)
            raise
        _end(p3)

        # ---- Phase 4: fire ----
        p4 = _begin("grab_fire")
        try:
            grab = await damai_grab(
                device_id=device_id,
                item_id=item_id,
                price_index=price_index,
                viewer_names=viewer_names or [],
                ticket_num=ticket_num,
                open_time=open_time,  # damai_grab handles its own open-time gate
                preheat_seconds=0.0,  # checklist already preheated
                max_runtime_sec=60.0,  # short window — already preheated
            )
            result.grab_result = grab
            result.status = grab.get("status", "submitted")
        except Exception as exc:
            result.status = "failed"
            result.error = f"grab_error: {exc}"
        _end(p4)
    else:
        # No open_time or preheat disabled — fire immediately
        p4 = _begin("grab_fire", "no open_time -> immediate")
        try:
            grab = await damai_grab(
                device_id=device_id,
                item_id=item_id,
                price_index=price_index,
                viewer_names=viewer_names or [],
                ticket_num=ticket_num,
                open_time="",
                preheat_seconds=0.0,
                max_runtime_sec=60.0,
            )
            result.grab_result = grab
            result.status = grab.get("status", "submitted")
        except Exception as exc:
            result.status = "failed"
            result.error = f"grab_error: {exc}"
        _end(p4)

    return result


async def _safe_cb(cb: Callable[..., Awaitable[None]], *args: Any) -> None:
    """Run an async callback without letting exceptions bubble."""
    try:
        await cb(*args)
    except Exception:
        logger.exception("checklist callback failed")
