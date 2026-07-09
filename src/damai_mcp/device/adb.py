"""Thin async wrapper around the adb CLI.

We deliberately avoid using adb_shell / aioadb because:
  * the local adb.exe that ships with 雷电 / MuMu / 真机 is what users actually have
  * pure-Python adb lacks some MediaTek-specific shell commands
  * we want zero extra binary downloads beyond `pip install damai-mcp`

`adb` must be on PATH; on Windows that means either SDK platform-tools or the
emulator's bundled adb (e.g. `C:/Program Files/LDPlayer/ldadb.exe`).
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..utils.errors import ADBError
from ..utils.logging import logger

_ADB_BIN = "adb.exe" if sys.platform == "win32" else "adb"


@dataclass(slots=True)
class ADBResult:
    """Result of a single adb invocation.

    `stdout_bytes` is the raw bytes from the subprocess. `stdout` is the
    utf-8-decoded text view (replacement-char on bad bytes). Use the former
    for binary commands like `screencap` / `cat` of an image file.
    """

    stdout_bytes: bytes
    stderr_bytes: bytes
    returncode: int
    duration_ms: int

    @property
    def stdout(self) -> str:
        return self.stdout_bytes.decode("utf-8", errors="replace")

    @property
    def stderr(self) -> str:
        return self.stderr_bytes.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def which_adb() -> str | None:
    """Locate the adb binary. Returns full path or None if not found."""
    found = shutil.which(_ADB_BIN)
    if found:
        return found
    # Common emulator-bundled locations
    candidates = [
        Path("C:/Program Files/LDPlayer") / _ADB_BIN,
        Path("C:/Program Files/Nox/bin") / _ADB_BIN,
        Path("C:/Program Files/MuMu") / _ADB_BIN,
        Path("C:/platform-tools") / _ADB_BIN,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


async def adb(
    *args: str,
    device_id: str | None = None,
    timeout: float = 30.0,
    check: bool = True,
    input_data: bytes | None = None,
) -> ADBResult:
    """Run an adb command asynchronously.

    Args:
        *args: subcommand + args, e.g. "shell", "input", "tap", "100", "200".
        device_id: target device serial; omit to talk to the only connected one.
        timeout: seconds.
        check: if True, raise ADBError on non-zero exit.
        input_data: stdin bytes (rarely used).

    Returns:
        ADBResult with stdout/stderr/returncode/duration.
    """
    bin_path = which_adb()
    if bin_path is None:
        raise ADBError(
            "adb 未找到。请安装 Android Platform Tools 或配置模拟器自带的 adb 到 PATH。"
        )

    cmd: list[str] = [bin_path]
    if device_id:
        cmd += ["-s", device_id]
    cmd += list(args)

    t0 = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input_data), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        raise ADBError(f"adb 命令超时（>{timeout}s）: {' '.join(cmd)}") from exc
    except FileNotFoundError as exc:
        raise ADBError(f"adb 二进制无法执行: {bin_path}") from exc

    duration_ms = int((time.perf_counter() - t0) * 1000)
    result = ADBResult(
        stdout_bytes=stdout_b,
        stderr_bytes=stderr_b,
        returncode=proc.returncode or 0,
        duration_ms=duration_ms,
    )

    if check and not result.ok:
        # "device not found" / "device offline" → DeviceNotFoundError would be
        # nicer, but we keep it as ADBError and let callers branch on stderr.
        snippet = (result.stderr or result.stdout).strip().splitlines()[-1] if (
            result.stderr or result.stdout
        ) else "no output"
        raise ADBError(f"adb 失败（rc={result.returncode}）: {snippet[:200]}")

    if duration_ms > 1000:
        logger.debug(f"adb {' '.join(cmd[1:6])} took {duration_ms}ms")

    return result


async def shell(
    *cmd: str,
    device_id: str | None = None,
    timeout: float = 30.0,
    check: bool = True,
) -> str:
    """Convenience: `adb [-s DEV] shell <cmd...>` and return stdout."""
    result = await adb("shell", *cmd, device_id=device_id, timeout=timeout, check=check)
    return result.stdout.rstrip("\r\n")


__all__ = ["ADBResult", "adb", "shell", "which_adb"]
