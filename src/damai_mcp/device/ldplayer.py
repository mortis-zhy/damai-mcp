"""LDPlayer lifecycle helpers.

The MCP actions operate on an already-connected ADB serial, but the original
project workflow also needs to start a named LDPlayer instance first. This
module keeps that host-side step explicit and non-destructive.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..utils.errors import ADBError
from .adb import adb, which_adb


@dataclass(frozen=True, slots=True)
class LDPlayerInstance:
    """Mapping between an LDPlayer index/name and its ADB serial."""

    index: int
    name: str
    device_id: str
    package: str = "cn.damai"


def candidate_device_ids(index: int, requested_device_id: str = "") -> tuple[str, ...]:
    """Return likely ADB serials for an LDPlayer multi-instance index."""
    candidates = [
        f"emulator-{5554 + index * 2}",
        f"127.0.0.1:{5555 + index * 2}",
    ]
    if requested_device_id and requested_device_id.lower() != "auto":
        candidates.append(requested_device_id)
    return tuple(dict.fromkeys(candidates))


async def _connected_device_ids() -> set[str]:
    result = await adb("devices", "-l", check=False, timeout=5.0)
    return {
        line.split()[0]
        for line in result.stdout.splitlines()[1:]
        if len(line.split()) >= 2 and line.split()[1] == "device"
    }


def which_ldconsole() -> str | None:
    """Locate LDPlayer's host controller executable."""
    binary = "ldconsole.exe" if sys.platform == "win32" else "ldconsole"
    found = shutil.which(binary)
    if found:
        return found
    for path in (
        Path("D:/leidian/LDPlayer9") / binary,
        Path("C:/Program Files/LDPlayer") / binary,
        Path("C:/Program Files/LDPlayer9") / binary,
    ):
        if path.exists():
            return str(path)
    return None


async def _run_ldconsole(*args: str, timeout: float = 30.0) -> str:
    path = which_ldconsole()
    if path is None:
        raise ADBError("未找到 ldconsole.exe，请安装雷电 9 或配置 LDPlayer 路径")
    proc = await asyncio.create_subprocess_exec(
        path, *args,
        # ldconsole can spawn a child that inherits its output handles.
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ADBError(f"ldconsole 命令超时: {' '.join(args)}") from exc
    stdout = stderr = b""
    if proc.returncode not in (0, None):
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise ADBError(f"ldconsole 失败 (rc={proc.returncode}): {detail[:300]}")
    return (stdout or b"").decode("utf-8", errors="replace").strip()


async def launch_instance(
    instance: LDPlayerInstance,
    *,
    adb_timeout: float = 60.0,
    connect_interval: float = 1.0,
) -> dict[str, object]:
    """Launch an instance and discover its ADB serial without changing it."""
    await _run_ldconsole("launch", "--index", str(instance.index), timeout=20.0)
    deadline = time.monotonic() + adb_timeout
    last_error = ""
    candidates = candidate_device_ids(instance.index, instance.device_id)
    connect_attempted = False
    while time.monotonic() < deadline:
        try:
            connected = await _connected_device_ids()
            device_id = next((serial for serial in candidates if serial in connected), None)
            if device_id:
                native_bridge = await _native_bridge_enabled(device_id)
                return {
                    "index": instance.index,
                    "name": instance.name,
                    "device_id": device_id,
                    "package": instance.package,
                    "adb_path": which_adb(),
                    "houdini": native_bridge,
                }
            if not connect_attempted:
                result = await adb("connect", candidates[1], check=False, timeout=5.0)
                last_error = f"{result.stdout} {result.stderr}".strip()
                connect_attempted = True
            else:
                last_error = f"connected devices: {sorted(connected)}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        await asyncio.sleep(connect_interval)
    raise ADBError(
        f"雷电实例 {instance.name or instance.index} 启动后未连接 ADB: {instance.device_id}; {last_error}"
    )


async def _native_bridge_enabled(device_id: str) -> bool:
    """Read the emulator's ARM bridge state without altering ISA properties."""
    result = await adb(
        "shell", "getprop", "persist.sys.nativebridge",
        device_id=device_id, check=False, timeout=5,
    )
    return result.ok and result.stdout.strip() not in {"", "0"}


__all__ = ["LDPlayerInstance", "candidate_device_ids", "launch_instance", "which_ldconsole"]
