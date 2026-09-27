from damai_mcp.device.ldplayer import candidate_device_ids


def test_ldplayer_index_one_prefers_stable_emulator_serial():
    assert candidate_device_ids(1) == ("emulator-5556", "127.0.0.1:5557")


def test_ldplayer_keeps_explicit_serial_as_fallback():
    assert candidate_device_ids(1, "custom-device") == (
        "emulator-5556",
        "127.0.0.1:5557",
        "custom-device",
    )
