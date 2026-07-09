"""Device manager: discovers and tracks connected Android devices/emulators.

Maintains an in-memory registry keyed by device_id so we don't shell out to
`adb devices` on every action call.

Threading model: this module is safe to share across async tasks because all
mutations happen behind the registry lock. Subprocess calls happen via
`adb()` which is itself stateless — we never hold a long-lived adb process.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from ..utils.errors import ADBError, DeviceNotFoundError
from ..utils.logging import logger
from .adb import adb, shell


@dataclass(slots=True)
class DeviceInfo:
    """Snapshot of an Android device's runtime state."""

    device_id: str
    state: str  # "device" | "offline" | "unauthorized"
    model: str = ""
    android_version: str = ""
    sdk: str = ""
    abi: str = ""
    screen_size: str = ""  # e.g. "1080x2400"
    total_mem_mb: int = 0
    is_emulator: bool = False
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "state": self.state,
            "model": self.model,
            "android_version": self.android_version,
            "sdk": self.sdk,
            "abi": self.abi,
            "screen_size": self.screen_size,
            "total_mem_mb": self.total_mem_mb,
            "is_emulator": self.is_emulator,
            "last_seen": self.last_seen,
        }


class DeviceManager:
    """Singleton-ish manager; access via `DeviceManager.shared()`."""

    _instance: DeviceManager | None = None

    def __init__(self) -> None:
        self._cache: dict[str, DeviceInfo] = {}
        self._lock = asyncio.Lock()
        self._refresh_ttl = 5.0  # seconds before re-querying adb devices
        self._last_refresh = 0.0

    @classmethod
    def shared(cls) -> DeviceManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---- discovery ----------------------------------------------------------

    async def list_devices(self, refresh: bool = False) -> list[DeviceInfo]:
        """Return all currently connected devices.

        Caches for 5 s; pass refresh=True to bypass cache.
        """
        now = time.monotonic()
        if not refresh and (now - self._last_refresh) < self._refresh_ttl and self._cache:
            return list(self._cache.values())

        try:
            result = await adb("devices", "-l", check=False, timeout=10)
        except ADBError as exc:
            logger.warning(f"adb devices 失败: {exc}")
            return list(self._cache.values())

        new_cache: dict[str, DeviceInfo] = {}
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line or "List of devices" in line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            if state not in ("device",):
                # Skip "offline" / "unauthorized"
                continue
            info = await self._build_info(serial, state)
            new_cache[serial] = info

        async with self._lock:
            self._cache = new_cache
            self._last_refresh = now
        return list(new_cache.values())

    async def _build_info(self, device_id: str, state: str) -> DeviceInfo:
        """Fill DeviceInfo with ro.* props. Failures yield partial info."""
        info = DeviceInfo(device_id=device_id, state=state)

        async def _safe_get(*args: str) -> str:
            try:
                result = await shell(*args, device_id=device_id, timeout=5, check=False)
                return result.strip()
            except Exception:  # noqa: BLE001
                return ""

        info.model = await _safe_get("getprop", "ro.product.model")
        info.android_version = await _safe_get("getprop", "ro.build.version.release")
        info.sdk = await _safe_get("getprop", "ro.build.version.sdk")
        info.abi = await _safe_get("getprop", "ro.product.cpu.abi")
        info.screen_size = await _safe_get("wm", "size")
        info.is_emulator = (
            "emulator" in device_id.lower()
            or "sdk_gphone" in (await _safe_get("getprop", "ro.product.device")).lower()
        )
        try:
            meminfo = await _safe_get("cat", "/proc/meminfo")
            if "MemTotal:" in meminfo:
                mem_kb = int(meminfo.split("MemTotal:")[1].split()[0])
                info.total_mem_mb = mem_kb // 1024
        except (IndexError, ValueError):
            pass
        return info

    # ---- connection control -------------------------------------------------

    async def connect(self, host_port: str) -> DeviceInfo:
        """Connect to a TCP-attached device (e.g. emulator at 127.0.0.1:5555).

        Returns the DeviceInfo if successful.
        """
        result = await adb("connect", host_port, check=False, timeout=10)
        if "connected" not in result.stdout.lower() and "already" not in result.stdout.lower():
            raise ADBError(f"adb connect 失败: {result.stdout.strip()} {result.stderr.strip()}")
        logger.info(f"已连接: {host_port}")
        await self.list_devices(refresh=True)
        info = self._cache.get(host_port)
        if not info:
            raise ADBError(f"连接后未在 adb devices 看到: {host_port}")
        return info

    async def disconnect(self, device_id: str) -> None:
        await adb("disconnect", device_id, check=False, timeout=5)
        async with self._lock:
            self._cache.pop(device_id, None)
        logger.info(f"已断开: {device_id}")

    # ---- accessors -----------------------------------------------------------

    async def get(self, device_id: str, refresh: bool = False) -> DeviceInfo:
        info = await self.list_devices(refresh=refresh)
        for d in info:
            if d.device_id == device_id:
                return d
        raise DeviceNotFoundError(f"设备未连接: {device_id}")

    async def require(self, device_id: str) -> DeviceInfo:
        """Resolve device, raising if it disappears between calls."""
        try:
            return await self.get(device_id)
        except DeviceNotFoundError:
            # Force one more refresh in case device just connected
            return await self.get(device_id, refresh=True)

    def cached_get(self, device_id: str) -> DeviceInfo | None:
        """Synchronous cache lookup; doesn't trigger adb."""
        return self._cache.get(device_id)


__all__ = ["DeviceInfo", "DeviceManager"]
