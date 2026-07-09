"""Tests for ADB plumbing — these run *without* a connected device.

We mock asyncio.create_subprocess_exec + which_adb so tests are hermetic.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from damai_mcp.device.adb import ADBResult, adb, shell, which_adb
from damai_mcp.utils.errors import ADBError


def _fake_proc(stdout: bytes = b"", stderr: bytes = b"", rc: int = 0):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = rc
    return proc


@pytest.fixture
def fake_adb_bin():
    """Mock which_adb so adb() can run without a real binary."""
    with patch("damai_mcp.device.adb.which_adb", return_value="/fake/adb"):
        yield "/fake/adb"


@pytest.mark.asyncio
async def test_which_adb_finds_shutil():
    with patch("shutil.which", return_value="/usr/bin/adb"):
        assert which_adb() == "/usr/bin/adb"


@pytest.mark.asyncio
async def test_which_adb_falls_back_to_emulator_path():
    with patch("shutil.which", return_value=None), \
         patch("pathlib.Path.exists", return_value=True):
        assert which_adb() is not None


@pytest.mark.asyncio
async def test_adb_success_returns_stdout(fake_adb_bin):
    fake = _fake_proc(stdout=b"hello\n", rc=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake)):
        result = await adb("devices", check=False)
    assert isinstance(result, ADBResult)
    assert result.stdout == "hello\n"
    assert result.returncode == 0
    assert result.stdout_bytes == b"hello\n"


@pytest.mark.asyncio
async def test_adb_binary_stdout_preserved(fake_adb_bin):
    """screencap returns PNG bytes — must NOT be utf-8 decoded."""
    fake = _fake_proc(stdout=b"\x89PNG\r\n\x1a\nFAKE", rc=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake)):
        result = await adb("exec-out", "screencap", "-p", check=False)
    assert result.stdout_bytes.startswith(b"\x89PNG")
    # The decoded view should also work (replacement-char)
    assert "PNG" in result.stdout


@pytest.mark.asyncio
async def test_adb_nonzero_raises_when_check_true(fake_adb_bin):
    fake = _fake_proc(stderr=b"device not found", rc=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake)):
        with pytest.raises(ADBError, match="device not found"):
            await adb("shell", "ls", check=True)


@pytest.mark.asyncio
async def test_adb_nonzero_silent_when_check_false(fake_adb_bin):
    fake = _fake_proc(stderr=b"oops", rc=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake)):
        result = await adb("shell", "ls", check=False)
    assert result.returncode == 1
    assert "oops" in result.stderr


@pytest.mark.asyncio
async def test_adb_missing_binary_raises_adberror():
    with patch("damai_mcp.device.adb.which_adb", return_value=None):
        with pytest.raises(ADBError, match="adb 未找到"):
            await adb("devices")


@pytest.mark.asyncio
async def test_shell_returns_stdout(fake_adb_bin):
    fake = _fake_proc(stdout=b"uid=0\n", rc=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake)):
        out = await shell("id")
    assert out == "uid=0"


@pytest.mark.asyncio
async def test_adb_timeout_raises(fake_adb_bin):
    fake = MagicMock()
    fake.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    fake.returncode = None
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake)):
        with pytest.raises(ADBError, match="超时"):
            await adb("shell", "sleep", "999", timeout=0.1)
