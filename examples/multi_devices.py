"""Example: grab a ticket using multiple devices/accounts concurrently.

Each emulator at a different ADB port runs its own 大麦 instance. We fire
`damai_grab` in parallel via asyncio.gather and print who wins.

Usage:
    # 1. Start two emulators on different ports:
    #    ldconsole launch --index 0    # port 5555
    #    ldconsole launch --index 1    # port 5557 (auto)
    # 2. Log into 大麦 on each (scan QR once)
    # 3. Run:
    python examples/multi_devices.py --item 1063631004645 --price 2 \\
        --open "2026-07-09 17:21:00"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from damai_mcp.damai.actions import damai_grab  # noqa: E402
from damai_mcp.utils.logging import configure as configure_logging  # noqa: E402

DEFAULT_ACCOUNTS = [
    {"device_id": "127.0.0.1:5555", "viewer_names": ["杨安琪"]},
    # {"device_id": "127.0.0.1:5557", "viewer_names": ["张三"]},
    # {"device_id": "127.0.0.1:5559", "viewer_names": ["李四"]},
]


async def main_async(args: argparse.Namespace) -> int:
    configure_logging("INFO", Path("./logs"))

    accounts = [{"device_id": d, "viewer_names": [v]} for d, v in zip(args.devices, args.viewers)]
    if not accounts:
        accounts = DEFAULT_ACCOUNTS
    print(f"🚀 启动 {len(accounts)} 个 worker 并发抢票")

    # Pre-warm: parse target time once
    target_ts: float | None = None
    if args.open:
        from datetime import datetime
        target_ts = datetime.strptime(args.open, "%Y-%m-%d %H:%M:%S").timestamp()
        now = time.time()
        wait_sec = target_ts - now - args.preheat
        if wait_sec > 0:
            print(f"⏰ 距开票 {target_ts - now:.0f}s，等待 {wait_sec:.0f}s 后开抢（预热 {args.preheat}s）")
            await asyncio.sleep(wait_sec)

    tasks = [
        damai_grab(
            device_id=a["device_id"],
            item_id=args.item,
            price_index=args.price,
            viewer_names=a["viewer_names"],
            ticket_num=1,
            open_time=args.open,
            preheat_seconds=args.preheat,
        )
        for a in accounts
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    print(f"\n=== 抢票结果 ===")
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  [{i}] ❌ 异常: {r}")
        else:
            print(f"  [{i}] {r['status']}  ({r['elapsed_ms']}ms)  {r.get('error') or 'OK'}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--item", required=True)
    p.add_argument("--price", type=int, default=1)
    p.add_argument("--devices", nargs="+", default=[], help='设备 ID 列表，如 "127.0.0.1:5555 127.0.0.1:5557"')
    p.add_argument("--viewers", nargs="+", default=[], help="每个设备对应的观演人姓名")
    p.add_argument("--open", default="", help='开票时间 "YYYY-MM-DD HH:MM:SS"')
    p.add_argument("--preheat", type=float, default=30.0)
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()