"""Tests for atomic action functions — verify they call adb correctly."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from damai_mcp.actions.actions import (
    double_tap,
    input_text,
    long_press,
    press_key,
    screenshot,
    scroll,
    swipe,
    tap,
)


@pytest.mark.asyncio
async def test_tap_sends_input_tap():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await tap("DEV", 100, 200)
        m.assert_called_once()
        cmd = m.call_args.args[0]
        assert cmd == "input tap 100 200"


@pytest.mark.asyncio
async def test_tap_with_duration_uses_swipe():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await tap("DEV", 100, 200, duration_ms=500)
        cmd = m.call_args.args[0]
        assert cmd.startswith("input swipe")
        assert "500" in cmd


@pytest.mark.asyncio
async def test_double_tap_calls_tap_twice():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await double_tap("DEV", 100, 200)
        assert m.call_count == 2


@pytest.mark.asyncio
async def test_long_press_uses_long_swipe():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await long_press("DEV", 100, 200, duration_ms=1000)
        cmd = m.call_args.args[0]
        assert cmd.startswith("input swipe")
        assert cmd.endswith("1000")


@pytest.mark.asyncio
async def test_swipe_passes_duration():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await swipe("DEV", 0, 0, 100, 100, duration_ms=250)
        cmd = m.call_args.args[0]
        assert cmd == "input swipe 0 0 100 100 250"


@pytest.mark.asyncio
async def test_scroll_down_calls_swipe():
    calls = []

    async def fake_shell(*args, **kwargs):
        calls.append(args)
        if args and args[0] == "wm":
            return "Physical size: 1080x2400"
        return ""

    with patch("damai_mcp.actions.actions.shell", side_effect=fake_shell):
        await scroll("DEV", "down", 0.5)
    swipe_call = next(c for c in calls if len(c) >= 1 and c[0].startswith("input swipe"))
    assert "540" in swipe_call[0]  # center x
    assert "1200" in swipe_call[0]  # center y


@pytest.mark.asyncio
async def test_input_text_replaces_spaces_with_pct_s():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await input_text("DEV", "hello world")
        cmd = m.call_args.args[0]
        assert cmd == "input text hello%sworld"


@pytest.mark.asyncio
async def test_press_key_known_name():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await press_key("DEV", "home")
        cmd = m.call_args.args[0]
        assert cmd == "input keyevent 3"  # KEYCODE_HOME = 3


@pytest.mark.asyncio
async def test_press_key_unknown_raises():
    from damai_mcp.utils.errors import ADBError
    with pytest.raises(ADBError, match="未知按键"):
        await press_key("DEV", "no_such_key")


@pytest.mark.asyncio
async def test_press_key_int():
    with patch("damai_mcp.actions.actions.shell", AsyncMock()) as m:
        await press_key("DEV", 187)  # APP_SWITCH
        cmd = m.call_args.args[0]
        assert cmd == "input keyevent 187"


@pytest.mark.asyncio
async def test_screenshot_uses_exec_out():
    fake_result = MagicMock()
    fake_result.stdout_bytes = b"\x89PNG\r\n\x1a\nFAKE"
    fake_result.returncode = 0
    with patch("damai_mcp.actions.actions.adb", AsyncMock(return_value=fake_result)) as m:
        png = await screenshot("DEV")
        assert png.startswith(b"\x89PNG")
        assert m.call_args.args[:3] == ("exec-out", "screencap", "-p")
