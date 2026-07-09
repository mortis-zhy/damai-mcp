"""Example: drive the MCP server from a Python client (like Claude Code does).

Spawns `damai-mcp serve` over stdio, then makes a few tool calls and prints
the results. Demonstrates how external AI agents would interact with the server.

Usage:
    pip install -e .[dev]
    python examples/mcp_client_demo.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Show how to use the MCP client SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("需要安装 mcp 客户端: pip install mcp", file=sys.stderr)
    sys.exit(1)


async def main() -> None:
    server_params = StdioServerParameters(
        command="damai-mcp",
        args=["serve"],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            # List tools
            tools = await session.list_tools()
            print(f"📋 工具总数: {len(tools.tools)}")
            for t in tools.tools[:8]:
                print(f"  - {t.name}: {t.description[:60]}...")
            print(f"  ... (还有 {len(tools.tools) - 8} 个)")

            # Call list_devices
            print("\n🔌 调用 list_devices:")
            result = await session.call_tool("list_devices", {"refresh": True})
            for content in result.content:
                if hasattr(content, "text"):
                    print(f"  {content.text}")

            # Call find_text (will fail without device, but shows the call)
            print("\n🔍 调用 find_text:")
            try:
                result = await session.call_tool(
                    "find_text",
                    {"device_id": "127.0.0.1:5555", "text": "立即购买", "timeout": 2.0},
                )
                for content in result.content:
                    if hasattr(content, "text"):
                        print(f"  {content.text}")
            except Exception as exc:
                print(f"  (expected if no device): {exc}")


if __name__ == "__main__":
    asyncio.run(main())