"""Tests for the grab-day checklist orchestrator.

We avoid hitting ADB/the network by monkeypatching the heavy grab functions.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from damai_mcp.damai.checklist import (
    ChecklistResult,
    PhaseEvent,
    _countdown_loop,
    parse_open_time,
    run_checklist,
)

# ---- pure-function parsing ----------------------------------------------------

class TestParseOpenTime:
    def test_empty_returns_none(self):
        assert parse_open_time("") is None
        assert parse_open_time("now") is None
        assert parse_open_time("立即") is None

    def test_iso_with_space(self):
        dt = parse_open_time("2026-07-20 10:00:00")
        assert dt == datetime(2026, 7, 20, 10, 0, 0)

    @pytest.mark.parametrize("fmt", [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ])
    def test_round_trip(self, fmt):
        s = datetime(2026, 7, 20, 10, 30, 45).strftime(fmt)
        assert parse_open_time(s) == datetime(2026, 7, 20, 10, 30, 45)

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="无法解析"):
            parse_open_time("not-a-date")


# ---- countdown loop -----------------------------------------------------------

class TestCountdownLoop:
    @pytest.mark.asyncio
    async def test_runs_progress_callback(self):
        cb = AsyncMock()
        # Target 0.05s in future — should run at least 1 tick of 1s (last 10s window)
        target = asyncio.get_event_loop().time() + 0.05
        await _countdown_loop(target, progress_cb=cb)
        # Should not raise & should have returned after the small delay

    @pytest.mark.asyncio
    async def test_returns_early_on_stop(self):
        stop = asyncio.Event()
        stop.set()
        target = asyncio.get_event_loop().time() + 1000  # far future
        cb = AsyncMock()
        await _countdown_loop(target, progress_cb=cb, stop_event=stop)
        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_kill_wait(self):
        async def bad_cb(_left: float, _elapsed: int) -> None:
            raise RuntimeError("boom")

        target = asyncio.get_event_loop().time() + 0.05
        # Must not raise even though callback always raises
        await _countdown_loop(target, progress_cb=bad_cb)


# ---- run_checklist (mocked) ---------------------------------------------------

@pytest.fixture
def mock_grabbed(monkeypatch):
    """Patch damai_grab / damai_open_concert / damai_login_check so the
    orchestrator runs in-memory without ADB."""
    from damai_mcp.damai import checklist

    monkeypatch.setattr(
        checklist, "_import_actions",
        lambda: (
            AsyncMock(return_value={"logged_in": True}),  # login check
            AsyncMock(return_value={"opened": True}),     # open concert
            AsyncMock(return_value={                      # grab
                "status": "submitted",
                "elapsed_ms": 1234,
                "item_id": "999",
            }),
        ),
    )


@pytest.mark.asyncio
async def test_run_checklist_immediate(monkeypatch):
    """No open_time -> runs the whole flow in immediate mode."""
    from damai_mcp.damai import checklist as checklist_mod

    # Patch DeviceManager.require so we don't need a real device
    monkeypatch.setattr(
        "damai_mcp.device.manager.DeviceManager.shared",
        classmethod(lambda cls: _FakeDeviceManager()),
    )

    monkeypatch.setattr(
        checklist_mod, "damai_grab",
        AsyncMock(return_value={"status": "submitted", "elapsed_ms": 1, "item_id": "1"}),
    )
    monkeypatch.setattr(
        checklist_mod, "damai_login_check",
        AsyncMock(return_value={"logged_in": True}),
    )
    monkeypatch.setattr(checklist_mod, "damai_open_concert", AsyncMock())

    res = await run_checklist(
        device_id="127.0.0.1:5555",
        item_id="1",
        open_time="",  # immediate
        price_index=1,
        viewer_names=["张三"],
    )
    assert isinstance(res, ChecklistResult)
    phase_names = [p.phase for p in res.phases]
    assert "connectivity" in phase_names
    assert "login_check" in phase_names
    assert "grab_fire" in phase_names
    assert res.status == "submitted"


@pytest.mark.asyncio
async def test_run_checklist_failure_propagates(monkeypatch):
    from damai_mcp.damai import checklist as checklist_mod

    monkeypatch.setattr(
        "damai_mcp.device.manager.DeviceManager.shared",
        classmethod(lambda cls: _FakeDeviceManager()),
    )
    monkeypatch.setattr(
        checklist_mod, "damai_login_check",
        AsyncMock(return_value={"logged_in": True}),
    )
    monkeypatch.setattr(checklist_mod, "damai_open_concert", AsyncMock())

    async def boom(*_a, **_kw):
        raise RuntimeError("simulated network blip")

    monkeypatch.setattr(checklist_mod, "damai_grab", boom)

    res = await run_checklist(
        device_id="127.0.0.1:5555",
        item_id="1",
        open_time="",
    )
    assert res.status == "failed"
    assert "simulated network blip" in (res.error or "")


class _FakeDeviceInfo:
    """Minimal stand-in for DeviceManager.require()."""
    model = "Leidian"
    screen_size = "1080x1920"


class _FakeDeviceManager:
    """Singleton shim that returns the fake device info without ADB."""

    async def require(self, _device_id: str) -> _FakeDeviceInfo:
        return _FakeDeviceInfo()


def test_phase_event_serialization():
    ev = PhaseEvent(phase="login", started_at_ms=1000)
    ev.finished_at_ms = 1500
    d = ev.to_dict()
    assert d["phase"] == "login"
    assert d["started_at_ms"] == 1000
    assert d["finished_at_ms"] == 1500
    assert d["elapsed_ms"] == 500


def test_checklist_result_serialization():
    res = ChecklistResult(status="submitted")
    res.phases.append(PhaseEvent(phase="connectivity", started_at_ms=0))
    d = res.to_dict()
    assert d["status"] == "submitted"
    assert len(d["phases"]) == 1
    assert d["grab_result"] is None
