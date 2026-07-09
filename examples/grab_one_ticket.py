"""Example: grab a single ticket using damai-mcp directly (without MCP server).

Usage:
    python examples/grab_one_ticket.py --device 127.0.0.1:5555 --item 1063631004645 \\
        --price 2 --viewer "杨安琪" --open "2026-07-09 17:21:00"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from a checkout without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from damai_mcp.damai.actions import damai_grab  # noqa: E402
from damai_mcp.device.manager import DeviceManager  # noqa: E402
from damai_mcp.utils.logging import configure as configure_logging  # noqa: E402


async def main_async(args: argparse.Namespace) -> int:
    configure_logging("INFO", Path("./logs"))
    mgr = DeviceManager.shared()

    # Verify device first
    try:
        info = await mgr.require(args.device)
    except Exception as exc:
        print(f"❌ 设备不可用: {exc}", file=sys.stderr)
        return 2
    print(f"✅ 设备: {info.device_id}  {info.model}  {info.screen_size}")

    # Run grab
    result = await damai_grab(
        device_id=args.device,
        item_id=args.item,
        price_index=args.price,
        viewer_names=[args.viewer] if args.viewer else [],
        ticket_num=args.num,
        open_time=args.open,
        preheat_seconds=args.preheat,
    )

    print(f"\n=== 抢票结果 ===")
    for k, v in result.items():
        if k == "screenshots":
            print(f"  {k}: {len(v)} 张")
            for p in v:
                print(f"    - {p}")
        else:
            print(f"  {k}: {v}")
    return 0 if result["status"] == "submitted" else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True, help='设备 ID，如 "127.0.0.1:5555"')
    p.add_argument("--item", required=True, help="大麦 item id")
    p.add_argument("--price", type=int, default=1, help="票档序号 (1-based)")
    p.add_argument("--viewer", default="", help="观演人姓名")
    p.add_argument("--num", type=int, default=1, help="张数")
    p.add_argument("--open", default="", help='开票时间 "YYYY-MM-DD HH:MM:SS"（空=立即抢）')
    p.add_argument("--preheat", type=float, default=30.0, help="开票前预热秒数")
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()