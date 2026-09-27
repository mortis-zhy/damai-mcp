"""Tests for the speed optimizations (UI cache + batch adb + warmup)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from damai_mcp.actions.batch import batch_send, batch_swipe, batch_tap
from damai_mcp.utils.find_helpers import search_elements
from damai_mcp.utils.ui_cache import UICache

# ---- pure-function search helpers -----------------------------------------

class _El:
    """Minimal stand-in for UIElement with the fields search_elements reads."""

    def __init__(self, text="", resource_id="", bounds=(0, 0, 0, 0), clickable=False):
        self.text = text
        self.resource_id = resource_id
        self.bounds = bounds
        self.clickable = clickable


def test_search_by_text_exact():
    elements = [_El(text="立即购买"), _El(text="加入购物车")]
    found = search_elements(elements, text="立即购买")
    assert found is not None
    assert found.text == "立即购买"


def test_search_by_text_substring():
    elements = [_El(text="立即购买 ¥380")]
    found = search_elements(elements, text="立即购买", exact=False)
    assert found is not None


def test_search_by_text_miss():
    elements = [_El(text="Buy Now")]
    found = search_elements(elements, text="立即购买")
    assert found is None


def test_search_by_resource_id_exact():
    elements = [_El(resource_id="cn.damai:id/buy_button")]
    found = search_elements(elements, resource_id="cn.damai:id/buy_button")
    assert found is not None


def test_search_by_resource_id_suffix():
    elements = [_El(resource_id="cn.damai:id/buy_button")]
    found = search_elements(elements, resource_id="buy_button", exact=False)
    assert found is not None


def test_search_no_criteria_raises():
    with pytest.raises(ValueError, match="must supply"):
        search_elements([], )


# ---- batch input formatting -----------------------------------------------

class _FakeAdbResult:
    def __init__(self, ok=True):
        self.returncode = 0 if ok else 1
        self.stdout_bytes = b""
        self.stderr_bytes = b""

    @property
    def ok(self):  # noqa: D401
        return self.returncode == 0


@pytest.mark.asyncio
async def test_batch_tap_joins_into_one_shell(monkeypatch):
    captured = []

    async def fake_adb(*args, **kw):
        captured.append(args)
        return _FakeAdbResult()

    monkeypatch.setattr("damai_mcp.actions.batch.adb", fake_adb)
    await batch_tap("127.0.0.1:5555", [(100, 200), (300, 400), (500, 600)])
    # Should be ONE adb call, not three
    assert len(captured) == 1
    script = captured[0][1]
    assert "input tap 100 200" in script
    assert "input tap 300 400" in script
    assert "input tap 500 600" in script
    # All three joined by ;
    assert script.count("input tap") == 3


@pytest.mark.asyncio
async def test_batch_tap_with_delay(monkeypatch):
    captured = []

    async def fake_adb(*args, **kw):
        captured.append(args[1])
        return _FakeAdbResult()

    monkeypatch.setattr("damai_mcp.actions.batch.adb", fake_adb)
    await batch_tap("127.0.0.1:5555", [(100, 200), (300, 400)], delay_ms=50)
    script = captured[0]
    assert "input tap 100 200" in script
    assert "sleep 0.050" in script
    assert "input tap 300 400" in script


@pytest.mark.asyncio
async def test_batch_tap_empty(monkeypatch):
    called = []

    async def fake_adb(*a, **kw):
        called.append(True)
        return _FakeAdbResult()

    monkeypatch.setattr("damai_mcp.actions.batch.adb", fake_adb)
    await batch_tap("127.0.0.1:5555", [])
    assert not called  # no adb invocation


@pytest.mark.asyncio
async def test_batch_swipe_format(monkeypatch):
    captured = []

    async def fake_adb(*args, **kw):
        captured.append(args[1])
        return _FakeAdbResult()

    monkeypatch.setattr("damai_mcp.actions.batch.adb", fake_adb)
    await batch_swipe("127.0.0.1:5555", [
        (10, 20, 30, 40, 100),
        (50, 60, 70, 80, 200),
    ])
    assert "input swipe 10 20 30 40 100" in captured[0]
    assert "input swipe 50 60 70 80 200" in captured[0]


@pytest.mark.asyncio
async def test_batch_send_passthrough(monkeypatch):
    captured = []

    async def fake_adb(*args, **kw):
        captured.append(args)
        return _FakeAdbResult()

    monkeypatch.setattr("damai_mcp.actions.batch.adb", fake_adb)
    await batch_send("127.0.0.1:5555", "input tap 1 2; input tap 3 4")
    assert captured[0][1] == "input tap 1 2; input tap 3 4"


# ---- UI cache ------------------------------------------------------------

@pytest.mark.asyncio
async def test_ui_cache_miss_then_hit(monkeypatch):
    cache = UICache(ttl_sec=5.0)
    monkeypatch.setattr("damai_mcp.utils.ui_cache.dump_ui",
                        AsyncMock(return_value=[_El(text="buy")]))
    # Stable screencap fingerprint
    monkeypatch.setattr(
        "damai_mcp.utils.ui_cache.UICache._fingerprint",
        AsyncMock(return_value="hash-123"),
    )

    elems1 = await cache.get("127.0.0.1:5555")
    elems2 = await cache.get("127.0.0.1:5555")
    assert elems1 is elems2  # cached
    stats = cache.stats
    assert stats["misses"] >= 1
    assert stats["hits"] >= 1


@pytest.mark.asyncio
async def test_ui_cache_invalidate(monkeypatch):
    cache = UICache(ttl_sec=5.0)
    monkeypatch.setattr("damai_mcp.utils.ui_cache.dump_ui",
                        AsyncMock(return_value=[_El(text="buy")]))

    await cache.get("127.0.0.1:5555")
    cache.invalidate()
    await cache.get("127.0.0.1:5555")
    stats = cache.stats
    assert stats["misses"] == 2


@pytest.mark.asyncio
async def test_ui_cache_ttl_expiry(monkeypatch):
    cache = UICache(ttl_sec=0.05)  # very short TTL
    monkeypatch.setattr("damai_mcp.utils.ui_cache.dump_ui",
                        AsyncMock(return_value=[_El(text="buy")]))
    monkeypatch.setattr(
        "damai_mcp.utils.ui_cache.UICache._fingerprint",
        AsyncMock(return_value="hash-xyz"),
    )

    await cache.get("127.0.0.1:5555")
    await asyncio.sleep(0.1)
    await cache.get("127.0.0.1:5555")
    # After TTL expiry, cache should miss
    assert cache.stats["misses"] == 2


@pytest.mark.asyncio
async def test_ui_cache_concurrent_calls_share_one_dump(monkeypatch):
    cache = UICache(ttl_sec=5.0)
    dump_calls = 0

    async def fake_dump(_device_id):
        nonlocal dump_calls
        dump_calls += 1
        return [_El(text="x")]

    monkeypatch.setattr("damai_mcp.utils.ui_cache.dump_ui", fake_dump)
    monkeypatch.setattr(
        "damai_mcp.utils.ui_cache.UICache._fingerprint",
        AsyncMock(return_value="hash-x"),
    )

    # Fire 5 concurrent gets
    await asyncio.gather(*[cache.get("127.0.0.1:5555") for _ in range(5)])
    # Lock serializes them, so dumps happen at most twice (miss + hit)
    assert dump_calls <= 2
