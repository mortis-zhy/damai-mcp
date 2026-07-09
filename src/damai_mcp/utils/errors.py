"""Exception hierarchy for damai-mcp.

Catch the base `DamaiMCPError` for "anything went wrong".
Specific subclasses let callers (and MCP error responses) be more precise.
"""
from __future__ import annotations


class DamaiMCPError(Exception):
    """Base exception for all damai-mcp errors."""


class DeviceNotFoundError(DamaiMCPError):
    """Specified device_id is not in `adb devices`."""


class ADBError(DamaiMCPError):
    """adb command returned non-zero or produced an error message."""


class UIElementNotFoundError(DamaiMCPError):
    """find_by_* could not locate the requested element within timeout."""


class TimeoutError_(DamaiMCPError):  # noqa: A001  (shadow built-in is intentional)
    """Generic wait timeout — wraps asyncio.TimeoutError semantics."""


class AppNotRunningError(DamaiMCPError):
    """The expected app is not in the foreground / not running."""


class DamaiLoginExpiredError(DamaiMCPError):
    """大麦 login session expired; user must re-scan QR."""


class DamaiGrabFailedError(DamaiMCPError):
    """Could not complete the grab flow within retry budget."""


__all__ = [
    "DamaiMCPError",
    "DeviceNotFoundError",
    "ADBError",
    "UIElementNotFoundError",
    "TimeoutError_",
    "AppNotRunningError",
    "DamaiLoginExpiredError",
    "DamaiGrabFailedError",
]
