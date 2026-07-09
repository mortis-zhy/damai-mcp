"""Tests for damai business-layer helpers.

Mocks the device side entirely; only tests business logic.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from damai_mcp.damai.actions import _is_in_viewer_name_list, _parse_iso, _wait_until
from damai_mcp.damai.selectors import DamaiSelectors, GrabConfig


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
