"""Tests for damai business-layer helpers.

Mocks the device side entirely; only tests business logic.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from damai_mcp.damai import actions as damai_actions
from damai_mcp.damai.actions import _is_in_viewer_name_list, _parse_iso, _wait_until
from damai_mcp.damai.selectors import DamaiSelectors, GrabConfig
from damai_mcp.inspector.models import UIElement


def test_parse_iso():
    ts = _parse_iso("2026-07-09 17:21:00")
    assert ts == datetime(2026, 7, 9, 17, 21, 0)


def test_is_in_viewer_name_list_substring():
    assert _is_in_viewer_name_list("杨安琪 (实名)", ["杨安琪"])
    assert _is_in_viewer_name_list("杨安琪", ["杨安琪"])
    assert not _is_in_viewer_name_list("张三", ["杨安琪"])
    assert not _is_in_viewer_name_list("", ["杨安琪"])


@pytest.mark.asyncio
async def test_wait_until_returns_immediately_when_past():
    # Should not hang
    import time
    past = time.time() - 10
    t0 = time.time()
    await _wait_until(past)
    assert time.time() - t0 < 0.1


@pytest.mark.asyncio
async def test_wait_until_returns_when_reached():
    import time
    target = time.time() + 0.2
    await _wait_until(target)
    assert time.time() >= target


def test_grab_config_defaults():
    c = GrabConfig(device_id="X", item_id="Y")
    assert c.price_index == 1
    assert c.ticket_num == 1
    assert c.viewer_names == []
    assert c.preheat_seconds == 30.0
    assert c.max_runtime_sec == 600.0


def test_damai_selectors_can_be_overridden():
    s = DamaiSelectors(detail_buy_button="Buy Now")
    assert s.detail_buy_button == "Buy Now"
    # others keep defaults
    assert s.detail_buy_button_alt == "立即预订"


@pytest.mark.asyncio
async def test_login_check_recognizes_new_logged_out_label(monkeypatch):
    async def foreground(_: str) -> bool:
        return True

    async def text(_: str, value: str, *, timeout: float):
        return value == "立即登录"

    monkeypatch.setattr(damai_actions, "_is_damai_foreground", foreground)
    monkeypatch.setattr(damai_actions, "assert_text", text)

    result = await damai_actions.damai_login_check("emulator-5566")

    assert result["foreground"] is True
    assert result["logged_in"] is False


@pytest.mark.asyncio
async def test_login_check_stops_on_auth_or_security_activity(monkeypatch):
    async def foreground(_: str) -> bool:
        return True

    async def device_shell(*command: str, **_: object) -> str:
        assert command == ("dumpsys", "window", "windows")
        return "mCurrentFocus=cn.damai/com.alibaba.wireless.security.open.middletier.fc.ui.ContainerActivity"

    monkeypatch.setattr(damai_actions, "_is_damai_foreground", foreground)
    monkeypatch.setattr(damai_actions, "shell", device_shell)

    result = await damai_actions.damai_login_check("emulator-5566")

    assert result["logged_in"] is False
    assert result["user_hint"]


@pytest.mark.asyncio
async def test_grab_stops_before_order_confirmation_by_default(monkeypatch, tmp_path):
    buy_button = UIElement(tag="node", text="Buy", bounds=(0, 0, 10, 10))
    monkeypatch.setattr(damai_actions, "damai_login_check", AsyncMock(return_value={"logged_in": True}))
    monkeypatch.setattr(damai_actions, "damai_open_concert", AsyncMock(return_value={"loaded": True}))
    monkeypatch.setattr(damai_actions, "wait_for_element", AsyncMock(return_value=buy_button))
    monkeypatch.setattr(damai_actions, "tap", AsyncMock())
    monkeypatch.setattr(damai_actions, "damai_select_price", AsyncMock())
    monkeypatch.setattr(damai_actions, "damai_select_viewers", AsyncMock())
    confirm = AsyncMock()
    monkeypatch.setattr(damai_actions, "damai_confirm_order", confirm)
    monkeypatch.setattr(damai_actions, "screenshot", AsyncMock())
    monkeypatch.setattr(damai_actions, "_shots_dir", lambda: tmp_path)

    result = await damai_actions.damai_grab("device", "item", viewer_names=["viewer"])

    assert result["status"] == "ready_for_human"
    assert result["requires_human_confirmation"] is True
    assert result["payment_started"] is False
    confirm.assert_not_awaited()
