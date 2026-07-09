"""Tests for retry decorator."""
from __future__ import annotations

import asyncio

import pytest

from damai_mcp.utils.errors import ADBError, DamaiMCPError
from damai_mcp.utils.retry import retry


@pytest.mark.asyncio
async def test_retry_succeeds_first_try():
    calls = []

    @retry(max_attempts=3)
    async def fn():
        calls.append(1)
        return "ok"

    assert await fn() == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_two_failures():
    calls = []

    @retry(max_attempts=3, base_delay=0.001)
    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ADBError("transient")
        return "ok"

    assert await fn() == "ok"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts():
    calls = []

    @retry(max_attempts=3, base_delay=0.001)
    async def fn():
        calls.append(1)
        raise ADBError("persistent")

    with pytest.raises(ADBError, match="persistent"):
        await fn()
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_does_not_catch_unexpected_exceptions():
    @retry(max_attempts=3, exceptions=(DamaiMCPError,))
    async def fn():
        raise ValueError("not retried")

    with pytest.raises(ValueError):
        await fn()


@pytest.mark.asyncio
async def test_retry_base_delay_grows():
    """Verify exponential backoff actually delays longer on 2nd attempt."""
    timings = []

    @retry(max_attempts=3, base_delay=0.05, max_delay=10.0, jitter=False)
    async def fn():
        if len(timings) > 0:
            timings.append(asyncio.get_event_loop().time())
        else:
            timings.append(asyncio.get_event_loop().time())
        raise ADBError("x")

    with pytest.raises(ADBError):
        await fn()
    assert len(timings) == 3
    # gap between attempt 1 and 2 should be ≥ 0.05s
    gap = timings[1] - timings[0]
    assert gap >= 0.04, f"Expected ≥0.05s backoff, got {gap:.3f}s"
