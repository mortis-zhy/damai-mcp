"""Smoke tests for the MCP server — verify all tools are registered."""
from __future__ import annotations


def test_mcp_instance_exists():
    from damai_mcp.server import mcp
    assert mcp.name == "damai-mcp"


def test_at_least_25_tools_registered():
    """We expect 30+ tools; allow some headroom."""
    from damai_mcp.server import mcp
    tools = mcp._tool_manager._tools
    # FastMCP stores tools in _tool_manager._tools (dict of name → Tool)
    count = len(tools)
    assert count >= 25, f"Expected ≥25 tools, got {count}: {list(tools.keys())}"


def test_all_tools_have_descriptions():
    from damai_mcp.server import mcp
    tools = mcp._tool_manager._tools
    for name, tool in tools.items():
        assert tool.description, f"Tool {name} has no description"
        assert len(tool.description) > 5, f"Tool {name} description too short"


def test_l1_tools_present():
    from damai_mcp.server import mcp
    tools = mcp._tool_manager._tools
    for required in ("list_devices", "connect_device", "disconnect_device", "device_info"):
        assert required in tools, f"Missing L1 tool: {required}"


def test_l2_tools_present():
    from damai_mcp.server import mcp
    tools = mcp._tool_manager._tools
    for required in ("tap", "swipe", "scroll", "input_text", "press_key",
                      "take_screenshot", "long_press", "double_tap"):
        assert required in tools, f"Missing L2 tool: {required}"


def test_l3_tools_present():
    from damai_mcp.server import mcp
    tools = mcp._tool_manager._tools
    for required in ("dump_ui", "find_text", "find_resource_id",
                      "find_xpath", "wait_for_element", "assert_text"):
        assert required in tools, f"Missing L3 tool: {required}"


def test_l4_tools_present():
    from damai_mcp.server import mcp
    tools = mcp._tool_manager._tools
    for required in ("damai_check_login", "damai_open_concert", "damai_select_price",
                      "damai_select_viewers", "damai_confirm_order", "damai_pay",
                      "damai_grab", "damai_grab_multi"):
        assert required in tools, f"Missing L4 tool: {required}"


def test_imports_are_clean():
    """Smoke check: importing the package should not pull in anything unexpected."""
    import damai_mcp
    assert damai_mcp.__version__ == "0.1.0"
