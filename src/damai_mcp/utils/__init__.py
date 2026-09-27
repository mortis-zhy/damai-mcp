"""Utility helpers — logging, NTP sync, error formatting."""
from __future__ import annotations

from .errors import DamaiMCPError
from .logging import configure as configure_logging
from .logging import logger
from .ntp import (
    DEFAULT_NTP_SERVER,
    NtpResult,
    async_query,
    fetch_device_time,
    query,
    sync_device_clock,
)

__all__ = [
    "DamaiMCPError",
    "configure_logging",
    "logger",
    "NtpResult",
    "query",
    "async_query",
    "sync_device_clock",
    "fetch_device_time",
    "DEFAULT_NTP_SERVER",
]
