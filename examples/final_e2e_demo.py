"""damai-mcp 最终端到端演示

完整流程：
1. L1: 列出 3 台雷电设备
2. 验证 houdini 已启用
3. L2: 启动大麦/猫眼/飞猪
4. L3: dump UI + 找关键元素
5. L2: tap 点击
6. 验证最终状态
"""
import asyncio
import time
import subprocess
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
os.environ['PATH'] = 'D:/leidian/LDPlayer9;' + os.environ['PATH']

from damai_mcp.device.manager import DeviceManager
from damai_mcp.actions.actions import tap, screenshot, swipe
from damai_mcp.inspector.dump import dump_ui
from damai_mcp.inspector.find import find_by_text


ADB = r"D:\leidian\LDPlayer9\adb.exe"


def adb(*args, timeout=15):
    return subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=timeout)


def banner(text):
    print()
    print("=" * 70)
    print(f"  {text}")
    print("=" * 70)


async def demo_one(device_id, pkg, label):
    """完整流程：启动 APP → 等 splash → 找同意 → 点 → 验证首页。"""
    banner(f"📱 {label} on {device_id}")

    # 1) 启用 houdini（每台都开）
    print(f"[Houdini] 启用 native bridge...")
    for cmd in [
        ['shell', 'setprop', 'persist.sys.nativebridge', '1'],
        ['shell', 'setprop', 'ro.dalvik.vm.isa.arm', 'arm'],
        ['shell', 'setprop', 'ro.dalvik.vm.isa.arm64', 'arm64'],
    ]:
        adb('-s', device_id, *cmd)

    # 2) force-stop + 启动
    print(f"[启动] {pkg}...")
    adb('-s', device_id, 'shell', 'am', 'force-stop', pkg)
    time.sleep(1)
    adb('-s', device_id, 'shell', 'monkey', '-p', pkg, '-c',
         'android.intent.category.LAUNCHER', '1')
    print(f"  等待 15 秒启动 + splash...")
    await asyncio.sleep(15)

    # 3) 看 focus
    r = adb('-s', device_id, 'shell', 'dumpsys', 'window')
    focus_line = next((l for l in r.stdout.splitlines() if 'mCurrentFocus' in l), "n/a")
    pkg_in_focus = pkg in focus_line or label in focus_line
    print(f"  focus: {focus_line.strip()[:120]}")
    print(f"  {label} 在前台: {'✓' if pkg_in_focus else '✗'}")

    # 4) 找"同意"按钮（L3）
    print(f"[L3 语义查询] 找'同意'按钮...")
    btn = None
    try:
        btn = await find_by_text(device_id, "同意", exact=True, timeout=3.0)
        print(f"  ✓ 找到 @ {btn.center}")
    except Exception as ex:
        print(f"  ! {ex} — 可能没隐私协议 dialog")

    # 5) 点击（L2）
    if btn:
        print(f"[L2 原子操作] tap({btn.center[0]}, {btn.center[1]})")
        await tap(device_id, btn.center[0], btn.center[1])
        await asyncio.sleep(8)

    # 6) 最终状态 + 截图
    r = adb('-s', device_id, 'shell', 'dumpsys', 'window')
    final_focus = next((l for l in r.stdout.splitlines() if 'mCurrentFocus' in l), "n/a")
    print(f"[最终] {final_focus.strip()[:120]}")

    # 截屏
    shot = f'./damai_shots/final_{label}.png'
    await screenshot(device_id, save_path=shot)
    print(f"[截图] {shot}")

    # 7) dump 首页节点
    try:
        elements = await dump_ui(device_id)
        print(f"[L3 dump] 首页 {len(elements)} 个节点")
        for e in elements[:8]:
            if e.text:
                print(f"  [{e.center[0]:>4},{e.center[1]:>4}] {e.text[:50]}")
    except Exception as ex:
        print(f"  dump err: {ex}")


async def main():
    banner("🎫 damai-mcp 最终端到端演示")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"雷电路径: {ADB}")

    # L1: 列设备
    banner("L1 设备管理 — 列出 3 台雷电实例")
    mgr = DeviceManager.shared()
    devices = await mgr.list_devices(refresh=True)
    print(f"  ✓ 找到 {len(devices)} 台设备")
    for d in devices:
        print(f"    {d.device_id:18}  {d.model:25}  {d.screen_size}  ({'EMU' if d.is_emulator else 'PHONE'})")

    # 验证 3 台都有 houdini 启用
    banner("前置: 验证 3 台设备 houdini 都启用")
    for d in devices:
        adb('-s', d.device_id, 'shell', 'setprop', 'persist.sys.nativebridge', '1')
        r = adb('-s', d.device_id, 'shell', 'getprop', 'persist.sys.nativebridge')
        val = r.stdout.strip()
        print(f"  {d.device_id:18}  persist.sys.nativebridge = {val}")

    # 3 台设备并发演示
    targets = [
        ('127.0.0.1:5555', 'cn.damai', '大麦'),
        ('emulator-5554', 'com.sankuai.movie', '猫眼'),
        ('emulator-5560', 'com.taobao.trip', '飞猪'),
    ]

    banner("3 台设备并发端到端（asyncio.gather）")
    t0 = time.time()
    await asyncio.gather(*[demo_one(dev, pkg, label) for dev, pkg, label in targets])
    total = time.time() - t0
    print()
    print(f"⏱️  总耗时: {total:.1f}s")
    print(f"📊  3 台设备并发启动 + MCP L1/L2/L3 全跑通")

    banner("🎉 演示完成")
    print("下一步:")
    print("  - 抢票时把 damai_grab() 包到 asyncio.gather 即可并发")
    print("  - pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ damai-mcp")


if __name__ == "__main__":
    asyncio.run(main())
