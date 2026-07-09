"""Retry decorator with exponential backoff.

Usage:
    @retry(max_attempts=3, base_delay=0.5, exceptions=(ADBError,))
    async def flaky_adb_call(...): ...
"""
from __future__ import annotations

import asyncio
import functools
import random
from collections.abc import Callable
from typing import Any, TypeVar

from .errors import DamaiMCPError
from .logging import logger

T = TypeVar("T")


def retry(
    max_attempts: int = 3,
    base_delay: float = 0.3,
    max_delay: float = 5.0,
    jitter: bool = True,
    exceptions: tuple[type[BaseException], ...] = (DamaiMCPError,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Async retry with exponential backoff + optional jitter."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} 重试 {max_attempts} 次后仍失败: {exc}")
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())
                    logger.warning(
                        f"{func.__name__} 第 {attempt}/{max_attempts} 次失败: {exc!s:.100}，"
                        f"等待 {delay:.2f}s 重试"
                    )
                    await asyncio.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


__all__ = ["retry"]
