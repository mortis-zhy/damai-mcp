"""Centralized loguru configuration.

All modules import `logger` from here so the format / sinks are consistent.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_DEFAULT_FMT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}:{function}:{line}</cyan> - "
    "<level>{message}</level>"
)


def configure(level: str = "INFO", log_dir: Path | None = None) -> None:
    """Configure root logger once at startup.

    Idempotent — calling twice will not duplicate handlers.
    """
    logger.remove()
    logger.add(sys.stderr, level=level, format=_DEFAULT_FMT, colorize=True)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "damai_mcp_{time:YYYYMMDD}.log",
            level="DEBUG",
            rotation="20 MB",
            retention="7 days",
            encoding="utf-8",
            enqueue=True,
        )


__all__ = ["logger", "configure"]
