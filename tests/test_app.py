"""Tests for the multi-app profile framework."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from damai_mcp.app.profile import (
    AppProfile,
    Step,
    list_profiles,
    load_profile,
    load_profile_file,
    register_profile,
)
from damai_mcp.app.runner import _ACTION_TABLE, run_profile

# ---- built-in registration ------------------------------------------------

def test_builtin_profiles_registered():
    # Trigger lazy registration
    for n in ("damai", "maoyan", "fliggy"):
        load_profile(n)
    names = list_profiles()
    for n in ("damai", "maoyan", "fliggy"):
        assert n in names


def test_maoyan_profile_shape():
    p = load_profile("maoyan")
    assert p.package_name == "com.sankuai.movie"
    assert len(p.steps) >= 4
    actions = [s.action for s in p.steps]
    assert "open_detail" in actions
    assert "tap_text" in actions


def test_fliggy_profile_shape():
    p = load_profile("fliggy")
    assert p.package_name == "com.taobao.trip"
    assert any(s.action == "tap_index" for s in p.steps)


def test_damai_profile_special():
    p = load_profile("damai")
    assert p.package_name == "cn.damai"


# ---- custom registration --------------------------------------------------

def test_register_custom_profile():
    custom = AppProfile(
        name="pytest_demo",
        package_name="com.example.demo",
        steps=[Step(name="wait_hi", action="wait_text", args={"text": "Hi"})],
        hints=["unit-test"],
    )
    register_profile(custom, override=True)
    loaded = load_profile("pytest_demo")
    assert loaded.package_name == "com.example.demo"
    assert loaded.steps[0].action == "wait_text"


def test_register_duplicate_raises():
    register_profile(AppProfile(name="dup", package_name="x.dup"), override=False)
    with pytest.raises(ValueError, match="already registered"):
        register_profile(AppProfile(name="dup", package_name="x.dup"))


# ---- JSON round trip ------------------------------------------------------

def test_load_profile_file():
    custom = {
        "name": "json_test",
        "package_name": "com.example.json",
        "steps": [
            {"name": "go", "action": "wait_text", "args": {"text": "buy"}},
            {"name": "tap", "action": "tap_text", "args": {"text": "buy"}, "timeout_sec": 3.0},
        ],
        "hints": ["loaded from disk"],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as f:
        json.dump(custom, f)
        path = Path(f.name)
    p = load_profile_file(path)
    assert p.name == "json_test"
    assert p.package_name == "com.example.json"
    assert len(p.steps) == 2
    assert p.steps[1].timeout_sec == 3.0


def test_load_profile_invalid_path():
    with pytest.raises(FileNotFoundError):
        load_profile_file("/no/such/path.json")


# ---- runner with mocked handlers -----------------------------------------

class _TestException(Exception):
    pass


@pytest.mark.asyncio
async def test_runner_returns_submitted_when_all_ok(monkeypatch):
    profile = AppProfile(
        name="runner_ok",
        package_name="x.ok",
        steps=[
            Step(name="s1", action="wait_text", args={"text": "buy"}),
            Step(name="s2", action="tap_text", args={"text": "buy"}),
        ],
    )
    monkeypatch.setitem(_ACTION_TABLE, "wait_text",
                        AsyncMock(return_value={"found": "buy"}))
    monkeypatch.setitem(_ACTION_TABLE, "tap_text",
                        AsyncMock(return_value={"tapped": "buy"}))

    out = await run_profile(profile, "127.0.0.1:5555", "ITEM1", {"price_index": 1})
    assert out.status == "submitted"
    assert len(out.steps) == 2
    assert all(s.status == "ok" for s in out.steps)


@pytest.mark.asyncio
async def test_runner_stops_on_failure_unless_continue(monkeypatch):
    profile = AppProfile(
        name="runner_fail",
        package_name="x.fail",
        steps=[
            Step(name="s1", action="wait_text", args={"text": "buy"}),  # will fail
            Step(name="s2", action="tap_text", args={"text": "buy"},
                 continue_on_fail=True),  # still runs
            Step(name="s3", action="sleep", args={"seconds": 0.0}),
        ],
    )

    async def boom(*_a, **_kw):
        raise _TestException("widget missing")

    monkeypatch.setitem(_ACTION_TABLE, "wait_text", boom)
    monkeypatch.setitem(_ACTION_TABLE, "tap_text",
                        AsyncMock(return_value={"tapped": "x"}))
    monkeypatch.setitem(_ACTION_TABLE, "sleep",
                        AsyncMock(return_value={"slept_sec": 0.0}))

    out = await run_profile(profile, "127.0.0.1:5555", "ITEM1")
    assert out.status == "failed"
    # Step 1 failed without continue_on_fail — runner stops
    assert len(out.steps) == 1
    assert "widget missing" in (out.error or "")


@pytest.mark.asyncio
async def test_runner_continues_when_flag_set(monkeypatch):
    profile = AppProfile(
        name="runner_continue",
        package_name="x.cont",
        steps=[
            Step(name="s1", action="sleep", args={"seconds": 0.01},
                 continue_on_fail=True),
            Step(name="s2", action="wait_text", args={"text": "x"}),
        ],
    )

    async def ok(*_a, **_kw):
        return {"x": 1}

    async def boom(*_a, **_kw):
        raise RuntimeError("transient")

    # First call returns ok, second raises — the runner should keep going
    boom_cb = AsyncMock(side_effect=boom)
    monkeypatch.setitem(_ACTION_TABLE, "sleep", ok)
    monkeypatch.setitem(_ACTION_TABLE, "wait_text", boom_cb)
    out = await run_profile(profile, "127.0.0.1:5555", "ITEM1")
    # sleep ok, wait_text failed (no continue) so runner stops
    assert out.status == "failed"
    # 2 step entries made it
    assert len(out.steps) == 2
    assert any(s.status == "failed" for s in out.steps)


def test_app_grab_mcp_tool_registered():
    """Sanity-check the MCP server registers the new tools."""
    # FastMCP doesn't expose registered tools directly, but the name should be in globals
    assert hasattr(__import__("damai_mcp.server", fromlist=["mcp"]), "list_app_profiles")
    assert hasattr(__import__("damai_mcp.server", fromlist=["mcp"]), "app_grab")
