"""多设备 3-App 并发沙盒测试。

对于 3 个雷电实例：
- emulator-5556 → damai_bot (大麦)
- emulator-5558 → maoyan_bot (猫眼)
- emulator-5560 → fliggy_bot (飞猪)

每个实例：
1. 验证连接
2. 加载对应 profile
3. 跑 NTP 同步
4. 模拟 app-grab 流程（不真正抢票，只测框架）
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

# 让本地 src/ 优先于 site-packages
import sys
SRC = Path(__file__).parent.parent / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

from loguru import logger

from damai_mcp.app.profile import list_profiles, get_profile
from damai_mcp.utils.ntp import async_query


# 每个设备的配置
DEVICE_CONFIGS = [
    {
        "device_id": "emulator-5556",
        "expected_profile": "damai",
        "package": "cn.damai",
        "installed": True,
        "label": "大麦"
    },
    {
        "device_id": "emulator-5558",
        "expected_profile": "maoyan",
        "package": "com.sankuai.movie",
        "installed": False,  # 还没装
        "label": "猫眼"
    },
    {
        "device_id": "emulator-5560",
        "expected_profile": "fliggy",
        "package": "com.taobao.trip",
        "installed": False,
        "label": "飞猪"
    },
]


async def test_device(device: dict) -> dict:
    """对单个设备跑全套沙盒测试."""
    from damai_mcp.device.manager import DeviceManager
    from damai_mcp.utils.ui_cache import UICache
    from damai_mcp.actions.batch import batch_tap

    result = {
        "device_id": device["device_id"],
        "label": device["label"],
        "package": device["package"],
        "checks": {},
    }
    started = time.time()

    # 1. 设备可达
    try:
        info = await DeviceManager.shared().require(device["device_id"])
        result["checks"]["device_ok"] = {
            "ok": True,
            "model": info.model if hasattr(info, "model") else "unknown",
            "screen": info.screen_size if hasattr(info, "screen_size") else "unknown",
        }
    except Exception as exc:
        result["checks"]["device_ok"] = {"ok": False, "error": str(exc)[:100]}
        result["status"] = "device_failed"
        return result

    # 2. profile 加载
    try:
        profile = get_profile(device["expected_profile"])
        result["checks"]["profile_ok"] = {
            "ok": True,
            "name": profile.name,
            "package": profile.package_name,
            "steps": len(profile.steps),
        }
    except Exception as exc:
        result["checks"]["profile_ok"] = {"ok": False, "error": str(exc)[:100]}

    # 3. App 是否安装
    import shutil
    if shutil.which("adb") is None:
        from loguru import logger as _l
        _l.warning("adb not on PATH, skipping package check")
        result["checks"]["app_installed"] = {"ok": False, "error": "adb not on PATH"}
    else:
        try:
            from damai_mcp.device.adb import adb
            r = await adb(
                "shell", "pm", "list", "packages", device["package"],
                device_id=device["device_id"], timeout=5.0, check=False,
            )
            out = (r.stdout_bytes or b"").decode("utf-8", errors="ignore")
            is_installed = device["package"] in out
            result["checks"]["app_installed"] = {
                "ok": True,
                "installed": is_installed,
                "expected": device["installed"],
            }
        except Exception as exc:
            result["checks"]["app_installed"] = {"ok": False, "error": str(exc)[:100]}

    # 4. NTP 同步
    try:
        ntp = await async_query("pool.ntp.org", timeout_sec=3.0)
        result["checks"]["ntp_sync"] = {
            "ok": True,
            "offset_ms": round(ntp.offset_ms, 2),
            "delay_ms": round(ntp.delay_ms, 2),
        }
    except Exception as exc:
        result["checks"]["ntp_sync"] = {"ok": False, "error": str(exc)[:100]}

    # 5. 设备时钟
    try:
        from damai_mcp.utils.ntp import fetch_device_time
        device_t = await fetch_device_time(device["device_id"])
        result["checks"]["device_time"] = {
            "ok": True,
            "unix": device_t,
            "delta_from_host_ms": round((device_t - time.time()) * 1000, 2),
        }
    except Exception as exc:
        result["checks"]["device_time"] = {"ok": False, "error": str(exc)[:100]}

    # 6. UI cache 初始化（如果 App 没装就跳过 dump）
    cache = UICache(ttl_sec=2.0)
    if result["checks"].get("app_installed", {}).get("installed"):
        try:
            elements = await cache.get(device["device_id"])
            result["checks"]["ui_cache"] = {
                "ok": True,
                "elements_count": len(elements),
                "cache_stats": cache.stats,
            }
        except Exception as exc:
            result["checks"]["ui_cache"] = {"ok": False, "error": str(exc)[:100]}
    else:
        result["checks"]["ui_cache"] = {"ok": False, "skipped": "app not installed"}

    # 7. batch input (不依赖 App 也能跑)
    try:
        await batch_tap(device["device_id"], [(540, 100), (540, 200), (540, 300)])
        result["checks"]["batch_input"] = {"ok": True}
    except Exception as exc:
        result["checks"]["batch_input"] = {"ok": False, "error": str(exc)[:100]}

    result["elapsed_ms"] = round((time.time() - started) * 1000, 1)
    result["status"] = "ok"
    return result


async def main() -> int:
    print("=" * 60)
    print("DAMAI-MCP 3-APP SANDBOX TEST")
    print("=" * 60)
    print()
    started = time.time()

    # 并发跑 3 个设备
    results = await asyncio.gather(
        *[test_device(d) for d in DEVICE_CONFIGS],
        return_exceptions=True,
    )

    # 渲染结果
    import json
    print()
    for r in results:
        if isinstance(r, Exception):
            print(f"  ERROR: {r}")
            continue
        print(f"--- {r['label']} ({r['device_id']}) ---")
        print(f"  package: {r['package']}")
        print(f"  elapsed: {r['elapsed_ms']}ms")
        for k, v in r["checks"].items():
            mark = "OK" if v.get("ok") else "FAIL"
            note = ""
            if v.get("error"):
                note = f"  err={v['error']}"
            elif v.get("skipped"):
                note = f"  ({v['skipped']})"
            else:
                extra = {kk: vv for kk, vv in v.items() if kk != "ok"}
                if extra:
                    note = f"  {extra}"
            print(f"  [{mark}] {k}{note}")
        print()

    print(f"Total: {round((time.time() - started) * 1000, 1)}ms")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
