"""Tests for NTP sync.

Some tests need a real UDP exchange (they are marked ntp_live and skipped on
CI if NTP is unreachable).
"""
from __future__ import annotations

import pytest

from damai_mcp.utils.ntp import (
    DEFAULT_NTP_SERVER,
    NtpResult,
    _build_request,
    _ntp_secs_to_unix,
    _parse_transmit_ts,
    query,
)

# ---- pure-function parsing ------------------------------------------------

def test_build_request_length_and_li():
    pkt = _build_request()
    assert len(pkt) == 48
    # First byte: 0x1B -> 00 011 011 (LI=0, VN=3, Mode=3)
    assert pkt[0] == 0x1B


def test_parse_transmit_ts_returns_pair():
    pkt = bytearray(48)
    pkt[40] = 0
    pkt[41] = 0
    pkt[42] = 0
    pkt[43] = 0  # seconds = 0
    pkt[44] = 0
    pkt[45] = 0
    pkt[46] = 0
    pkt[47] = 0
    secs, frac = _parse_transmit_ts(bytes(pkt))
    assert secs == 0
    assert frac == 0


def test_ntp_secs_to_unix():
    # 2000-01-01 00:00 UTC = 946684800 unix = 3155673600 ntp
    secs, frac = 3_155_673_600, 0
    assert _ntp_secs_to_unix(secs, frac) == pytest.approx(946684800.0, abs=1e-6)


def test_ntp_secs_to_unix_with_fraction():
    secs = 3_155_673_600
    frac = 2**31  # 0.5 second
    val = _ntp_secs_to_unix(secs, frac)
    assert val == pytest.approx(946684800.5, abs=1e-6)


# ---- NtpResult dataclass --------------------------------------------------

def test_ntp_result_to_dict():
    r = NtpResult(
        server="pool.ntp.org",
        offset_ms=12.5,
        delay_ms=80.1,
        server_unix=1_700_000_000.0,
        queried_at_unix=1_700_000_000.1,
    )
    d = r.to_dict()
    assert d["server"] == "pool.ntp.org"
    assert d["offset_ms"] == 12.5
    assert d["synced"] is True
    assert d["server_unix"] == 1_700_000_000.0


@pytest.mark.parametrize("offset_ms, expected_synced", [
    (10.0, True),
    (200.0, True),
    (499.0, True),
    (501.0, False),
    (-499.0, True),
    (-501.0, False),
])
def test_ntp_result_synced(offset_ms, expected_synced):
    r = NtpResult(
        server="x", offset_ms=offset_ms, delay_ms=0,
        server_unix=0, queried_at_unix=0,
    )
    assert r.synced is expected_synced


# ---- mocked query (deterministic) ---------------------------------------

class _FakeUDPSocket:
    """Returns a fake NTP response on ``recvfrom``."""

    def __init__(self, response: bytes) -> None:
        self._response = response
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def settimeout(self, *_a) -> None:  # noqa: D401
        pass

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def recvfrom(self, _n: int) -> tuple[bytes, tuple[str, int]]:
        return self._response, ("192.0.2.1", 123)

    def close(self) -> None:
        pass


def _fake_ntp_response(seconds: int, fraction: int = 0) -> bytes:
    pkt = bytearray(48)
    pkt[0] = 0x1C  # server response
    pkt[40:44] = seconds.to_bytes(4, "big")
    pkt[44:48] = fraction.to_bytes(4, "big")
    return bytes(pkt)


def test_query_uses_sock(monkeypatch):
    # Construct an NTP packet that represents the current time
    import time as _time
    unix_now = int(_time.time())
    fake = _FakeUDPSocket(_fake_ntp_response(unix_now + 2_208_988_800))

    monkeypatch.setattr("damai_mcp.utils.ntp.socket.socket", lambda *a, **kw: fake)

    out = query("192.0.2.123", timeout=1.0)
    assert out.server == "192.0.2.123"
    # Offset should be small (sub-second) since the server time matches the
    # host time within round-trip delay.
    assert abs(out.offset_ms) < 5000
    # And we sent exactly 1 packet of 48 bytes
    assert len(fake.sent) == 1
    assert len(fake.sent[0][0]) == 48
    assert fake.sent[0][1] == ("192.0.2.123", 123)


def test_query_timeout(monkeypatch):
    """Simulated timeout — patch socket.socket so recvfrom raises TimeoutError."""
    class _S:
        def __init__(self, *a, **kw): pass
        def settimeout(self, *_a): pass
        def sendto(self, *a, **_kw): pass
        def recvfrom(self, *_a): raise TimeoutError("simulated")
        def close(self): pass

    monkeypatch.setattr("damai_mcp.utils.ntp.socket.socket", lambda *a, **kw: _S())
    with pytest.raises(TimeoutError, match="did not respond"):
        query("0.0.0.1", timeout=0.1)


def test_query_short_response(monkeypatch):
    fake = _FakeUDPSocket(b"\x00" * 16)  # only 16 bytes
    monkeypatch.setattr("damai_mcp.utils.ntp.socket.socket", lambda *a, **kw: fake)
    with pytest.raises(RuntimeError, match="too short"):
        query("0.0.0.2", timeout=0.1)


# ---- async_query ---------------------------------------------------------

@pytest.mark.asyncio
async def test_async_query_returns_ntp_result(monkeypatch):
    from damai_mcp.utils import ntp as ntp_mod

    class _StubResult(NtpResult):
        def __init__(self) -> None:
            super().__init__(
                server="stub", offset_ms=0.0, delay_ms=0.0,
                server_unix=0.0, queried_at_unix=0.0,
            )

    monkeypatch.setattr(ntp_mod, "query", lambda *a, **kw: _StubResult())
    out = await ntp_mod.async_query("pool.ntp.org", 1.0)
    assert isinstance(out, NtpResult)
    assert out.server == "stub"
    assert out.synced is True


def test_default_ntp_server_present():
    assert DEFAULT_NTP_SERVER == "pool.ntp.org"
