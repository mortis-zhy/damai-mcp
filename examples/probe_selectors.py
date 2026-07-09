"""Debug helper: dump current UI to inspect selectors used by 大麦.

When 大麦 updates and our hardcoded selectors drift, run this on the concert
page and update `damai_mcp/damai/selectors.py` accordingly.

Usage:
    python examples/probe_selectors.py --device 127.0.0.1:5555
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from damai_mcp.inspector.dump import dump_ui, dump_ui_to_file  # noqa: E402
from damai_mcp.utils.logging import configure as configure_logging  # noqa: E402


async def main_async(args: argparse.Namespace) -> None:
    configure_logging("INFO", Path("./logs"))

    print(f"📱 正在 dump 设备 {args.device} 的 UI...")
    elements = await dump_ui(args.device, compressed=not args.full)

    # Print all clickable elements with text or resource-id
    print(f"\n=== 可点击元素（共 {len(elements)} 个节点） ===")
    for el in elements:
        if el.clickable and (el.text or el.resource_id or el.content_desc):
            print(f"  [{el.center[0]:>4}, {el.center[1]:>4}]  "
                  f"text={el.text!r:20}  rid={el.resource_id!r:30}  "
                  f"class={el.class_name.split('.')[-1]}")

    # Save XML
    out = Path(args.out)
    await dump_ui_to_file(args.device, out)
    print(f"\n💾 XML 已保存: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True)
    p.add_argument("--out", default="./probe_ui.xml")
    p.add_argument("--full", action="store_true", help="不要 compressed 模式（更全但更慢）")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()