"""FastMCP server entry — registers all tools from all layers.

Run via:
    python -m damai_mcp                # stdio transport (default for Claude Code)
    damai-mcp serve --transport http   # HTTP transport
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .actions.actions import (
    double_tap as _double_tap,
)
from .actions.actions import (
    input_text as _input_text,
)
from .actions.actions import (
    long_press as _long_press,
)
from .actions.actions import (
    press_key as _press_key,
)
from .actions.actions import (
    screenshot as _screenshot,
)
from .actions.actions import (
    scroll as _scroll,
)
from .actions.actions import (
    swipe as _swipe,
)
from .actions.actions import (
    tap as _tap,
)
from .app import (
    list_profiles as _app_list_profiles,
)
from .app import (
    load_profile as _app_load_profile,
)
from .app import (
    run_profile as _app_run_profile,
)
from .damai.actions import (
    damai_confirm_order as _damai_confirm_order,
)
from .damai.actions import (
    damai_grab as _damai_grab,
)
from .damai.actions import (
    damai_login_check as _damai_login_check,
)
from .damai.actions import (
    damai_open_concert as _damai_open_concert,
)
from .damai.actions import (
    damai_pay as _damai_pay,
)
from .damai.actions import (
    damai_select_price as _damai_select_price,
)
from .damai.actions import (
    damai_select_viewers as _damai_select_viewers,
)
from .damai.checklist import run_checklist as _damai_run_checklist
from .damai.selectors import DamaiSelectors, GrabConfig  # noqa: F401
from .device.adb import which_adb as _which_adb
from .device.ldplayer import (
    LDPlayerInstance,
)
from .device.ldplayer import (
    launch_instance as _launch_ldplayer,
)
from .device.ldplayer import (
    which_ldconsole as _which_ldconsole,
)
from .device.manager import DeviceManager
from .inspector.dump import dump_ui as _dump_ui
from .inspector.dump import dump_ui_to_file as _dump_ui_to_file
from .inspector.find import assert_text as _assert_text
from .inspector.find import find_by_resource_id as _find_by_resource_id
from .inspector.find import find_by_text as _find_by_text
from .inspector.find import find_by_xpath as _find_by_xpath
from .inspector.find import wait_for_element as _wait_for_element
from .inspector.models import UIElement  # noqa: F401
from .utils.errors import DamaiMCPError  # noqa: F401
from .utils.logging import configure as configure_logging
from .utils.logging import logger
from .utils.ntp import (
    DEFAULT_NTP_SERVER as _DEFAULT_NTP_SERVER,
)
from .utils.ntp import (
    async_query as _ntp_async_query,
)
from .utils.ntp import (
    fetch_device_time as _ntp_fetch_device_time,
)

mcp = FastMCP(
    name="damai-mcp",
    instructions=(
        "damai-mcp 控制 Android 设备/模拟器，自动化抢大麦/猫眼/飞猪门票。"
        "工具分 4 层：L1 设备管理、L2 原子操作、L3 语义查询、L4 业务编排。"
        "先用 list_devices 看设备，再用对应层工具。"
    ),
)


# ============================================================================
# L1 — Device management
# ============================================================================

@mcp.tool()
async def list_devices(refresh: bool = False) -> dict[str, Any]:
    """列出所有连接的 Android 设备/模拟器。

    Args:
        refresh: 跳过缓存，强制重新查询 `adb devices`。
    """
    devices = await DeviceManager.shared().list_devices(refresh=refresh)
    return {
        "count": len(devices),
        "devices": [d.to_dict() for d in devices],
        "adb_path": _which_adb(),
    }


@mcp.tool()
async def connect_device(host_port: str) -> dict[str, Any]:
    """通过 TCP 连接远程设备/模拟器。

    Args:
        host_port: 形如 "127.0.0.1:5555"（雷电模拟器默认）。
    """
    info = await DeviceManager.shared().connect(host_port)
    return info.to_dict()


@mcp.tool()
async def disconnect_device(device_id: str) -> dict[str, Any]:
    """断开指定设备。

    Args:
        device_id: 设备序列号或 IP:端口。
    """
    await DeviceManager.shared().disconnect(device_id)
    return {"disconnected": device_id}


@mcp.tool()
async def device_info(device_id: str) -> dict[str, Any]:
    """获取设备的详细信息（型号、安卓版本、屏幕分辨率等）。

    Args:
        device_id: 设备 ID。
    """
    info = await DeviceManager.shared().require(device_id)
    return info.to_dict()


@mcp.tool()
async def launch_ldplayer(
    index: int = 1,
    name: str = "damai_bot",
    device_id: str = "auto",
    package: str = "cn.damai",
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    """启动雷电实例、连接 ADB，并启用大麦所需的 ARM/Houdini bridge。

    This only launches and connects an existing instance; it does not install
    APKs, clear app data, or perform destructive operations.
    """
    result = await _launch_ldplayer(
        LDPlayerInstance(index=index, name=name, device_id=device_id, package=package),
        adb_timeout=timeout_sec,
    )
    result["ldconsole_path"] = _which_ldconsole()
    return result


# ============================================================================
# L2 — Atomic actions
# ============================================================================

@mcp.tool()
async def tap(device_id: str, x: int, y: int, duration_ms: int = 50) -> dict[str, Any]:
    """点击屏幕坐标。

    Args:
        device_id: 设备 ID。
        x: 像素 X 坐标。
        y: 像素 Y 坐标。
        duration_ms: 按住时长（>0 模拟长按）。
    """
    await _tap(device_id, x, y, duration_ms=duration_ms)
    return {"tapped": [x, y], "duration_ms": duration_ms}


@mcp.tool()
async def double_tap(device_id: str, x: int, y: int, gap_ms: int = 80) -> dict[str, Any]:
    """双击。

    Args:
        device_id: 设备 ID。
        x, y: 坐标。
        gap_ms: 两次点击间隔毫秒。
    """
    await _double_tap(device_id, x, y, gap_ms=gap_ms)
    return {"double_tapped": [x, y]}


@mcp.tool()
async def long_press(device_id: str, x: int, y: int, duration_ms: int = 800) -> dict[str, Any]:
    """长按坐标。

    Args:
        device_id: 设备 ID。
        x, y: 坐标。
        duration_ms: 按住时长（500-1000ms 可触发长按菜单）。
    """
    await _long_press(device_id, x, y, duration_ms=duration_ms)
    return {"long_pressed": [x, y], "duration_ms": duration_ms}


@mcp.tool()
async def swipe(
    device_id: str,
    x1: int, y1: int, x2: int, y2: int,
    duration_ms: int = 300,
) -> dict[str, Any]:
    """从 (x1,y1) 拖动到 (x2,y2)。

    Args:
        device_id: 设备 ID。
        x1, y1, x2, y2: 起止坐标。
        duration_ms: 拖动时长。
    """
    await _swipe(device_id, x1, y1, x2, y2, duration_ms=duration_ms)
    return {"swiped": [[x1, y1], [x2, y2]], "duration_ms": duration_ms}


@mcp.tool()
async def scroll(
    device_id: str,
    direction: str = "down",
    distance_ratio: float = 0.6,
    duration_ms: int = 300,
) -> dict[str, Any]:
    """整屏滚动。

    Args:
        device_id: 设备 ID。
        direction: "up" | "down" | "left" | "right"。
        distance_ratio: 滚动距离占屏幕短边的比例（0-1）。
        duration_ms: 滚动时长。
    """
    await _scroll(device_id, direction, distance_ratio, duration_ms=duration_ms)
    return {"scrolled": direction, "distance_ratio": distance_ratio}


@mcp.tool()
async def input_text(device_id: str, text: str, delay_ms: int = 0) -> dict[str, Any]:
    """向当前焦点输入框输入文本（中文需要 ADBKeyBoard）。

    Args:
        device_id: 设备 ID。
        text: 要输入的文本。
        delay_ms: 字符间隔（用于绕过风控）。
    """
    await _input_text(device_id, text, delay_ms=delay_ms)
    return {"input_len": len(text), "text_preview": text[:30]}


@mcp.tool()
async def press_key(device_id: str, key: str) -> dict[str, Any]:
    """按键。

    Args:
        device_id: 设备 ID。
        key: 常用键名（home/back/menu/enter/delete/tab/up/down/left/right/
             volume_up/volume_down/power）。
    """
    await _press_key(device_id, key)
    return {"pressed": key}


@mcp.tool()
async def take_screenshot(
    device_id: str,
    save_path: str | None = None,
    return_base64: bool = False,
    max_width: int | None = None,
) -> dict[str, Any]:
    """截图。

    Args:
        device_id: 设备 ID。
        save_path: 保存路径（None 则不保存文件）。
        return_base64: True 则返回 base64 字符串（用于 AI 看图）。
        max_width: 缩放宽度（保持比例），None 不缩放。
    """
    max_size = (max_width, 99999) if max_width else None
    res = await _screenshot(
        device_id, save_path=save_path,
        return_base64=return_base64, max_size=max_size,
    )
    if return_base64:
        preview = res[:200] + "..." if isinstance(res, str) and len(res) > 200 else res
        return {"saved_to": save_path, "base64": preview, "len": len(res)}
    return {"saved_to": save_path, "bytes": len(res)}


# ============================================================================
# L3 — Semantic UI
# ============================================================================

@mcp.tool()
async def dump_ui(device_id: str, save_to: str | None = None) -> dict[str, Any]:
    """获取当前界面的 UI 层级。

    Args:
        device_id: 设备 ID。
        save_to: 保存 XML 快照到该路径，便于事后分析。
    """
    elements = await _dump_ui(device_id)
    if save_to:
        await _dump_ui_to_file(device_id, save_to)
    return {"count": len(elements), "elements": [e.to_dict() for e in elements[:200]]}


@mcp.tool()
async def find_text(
    device_id: str,
    text: str,
    exact: bool = True,
    clickable_only: bool = False,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """按文字查找 UI 元素。

    Args:
        device_id: 设备 ID。
        text: 要查找的文字（默认精确匹配）。
        exact: True=全等，False=子串匹配。
        clickable_only: 只返回可点击元素。
        timeout: 等待秒数。
    """
    el = await _find_by_text(device_id, text, exact=exact, clickable_only=clickable_only, timeout=timeout)
    return el.to_dict()


@mcp.tool()
async def find_resource_id(
    device_id: str,
    resource_id: str,
    exact: bool = True,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """按 resource-id 查找 UI 元素。

    Args:
        device_id: 设备 ID。
        resource_id: resource-id（默认精确匹配）。
        exact: True=全等，False=后缀匹配。
        timeout: 等待秒数。
    """
    el = await _find_by_resource_id(device_id, resource_id, exact=exact, timeout=timeout)
    return el.to_dict()


@mcp.tool()
async def find_xpath(device_id: str, xpath: str, timeout: float = 5.0) -> dict[str, Any]:
    """按 XPath 查找 UI 元素。

    Args:
        device_id: 设备 ID。
        xpath: lxml 风格 XPath，例如 "//node[@text='立即购买']"。
        timeout: 等待秒数。
    """
    el = await _find_by_xpath(device_id, xpath, timeout=timeout)
    return el.to_dict()


@mcp.tool()
async def wait_for_element(
    device_id: str,
    selector: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """等待元素出现，支持前缀：text= / resource-id= / xpath=。

    Args:
        device_id: 设备 ID。
        selector: 选择器（带前缀）或裸文字。
        timeout: 等待秒数。
    """
    el = await _wait_for_element(device_id, selector, timeout=timeout)
    return el.to_dict()


@mcp.tool()
async def assert_text(device_id: str, text: str, exact: bool = True, timeout: float = 3.0) -> dict[str, Any]:
    """断言文字在指定时间内出现（不抛异常）。

    Args:
        device_id: 设备 ID。
        text: 要检测的文字。
        exact: True=全等。
        timeout: 等待秒数。
    """
    found = await _assert_text(device_id, text, exact=exact, timeout=timeout)
    return {"found": found, "text": text}


# ============================================================================
# L4 — 大麦 business
# ============================================================================

@mcp.tool()
async def damai_check_login(device_id: str, timeout: float = 3.0) -> dict[str, Any]:
    """检查大麦是否在前台且已登录。

    Args:
        device_id: 设备 ID。
        timeout: 等待秒数。
    """
    return await _damai_login_check(device_id, timeout=timeout)


@mcp.tool()
async def damai_open_concert(device_id: str, item_id: str) -> dict[str, Any]:
    """打开大麦演出详情页。

    Args:
        device_id: 设备 ID。
        item_id: 大麦 item id（数字字符串）。
    """
    return await _damai_open_concert(device_id, item_id)


@mcp.tool()
async def damai_select_price(
    device_id: str,
    price_index: int = 1,
    timeout: float = 4.0,
) -> dict[str, Any]:
    """选择第 N 档票（从详情页的票价表）。

    Args:
        device_id: 设备 ID。
        price_index: 1-based 票档序号。
        timeout: 等待秒数。
    """
    el = await _damai_select_price(device_id, price_index, timeout=timeout)
    return {"selected_price_text": el.text, "center": list(el.center)}


@mcp.tool()
async def damai_select_viewers(
    device_id: str,
    viewer_names: list[str],
    timeout: float = 4.0,
) -> dict[str, Any]:
    """勾选观演人。

    Args:
        device_id: 设备 ID。
        viewer_names: 观演人姓名列表，如 ["杨安琪"]。
        timeout: 等待秒数。
    """
    clicked = await _damai_select_viewers(device_id, viewer_names, timeout=timeout)
    return {
        "requested": viewer_names,
        "clicked": len(clicked),
        "elements": [e.to_dict() for e in clicked],
    }


@mcp.tool()
async def damai_confirm_order(device_id: str, timeout: float = 5.0) -> dict[str, Any]:
    """点击「确认订单」按钮。

    Args:
        device_id: 设备 ID。
        timeout: 等待秒数。
    """
    el = await _damai_confirm_order(device_id, timeout=timeout)
    return el.to_dict()


@mcp.tool()
async def damai_pay(device_id: str, timeout: float = 5.0) -> dict[str, Any]:
    """点击「立即支付」按钮（后续需手动在大麦 APP 完成支付）。

    Args:
        device_id: 设备 ID。
        timeout: 等待秒数。
    """
    el = await _damai_pay(device_id, timeout=timeout)
    return el.to_dict()


@mcp.tool()
async def damai_grab(
    device_id: str,
    item_id: str,
    price_index: int = 1,
    viewer_names: list[str] | None = None,
    ticket_num: int = 1,
    open_time: str = "",
    preheat_seconds: float = 30.0,
    max_runtime_sec: float = 600.0,
    confirm_order: bool = False,
) -> dict[str, Any]:
    """一站式抢票：等开票 → 抢档位 → 选观演人 → 提交订单。

    Args:
        device_id: 设备 ID。
        item_id: 大麦 item id。
        price_index: 票档序号（1-based）。
        viewer_names: 观演人姓名列表。
        ticket_num: 张数。
        open_time: 开票时间 "YYYY-MM-DD HH:MM:SS"（空=立即抢）。
        preheat_seconds: 开票前多少秒开始预热（默认 30）。
        max_runtime_sec: 整个流程最大耗时（默认 600 秒）。
    """
    return await _damai_grab(
        device_id=device_id,
        item_id=item_id,
        price_index=price_index,
        viewer_names=viewer_names or [],
        ticket_num=ticket_num,
        open_time=open_time,
        preheat_seconds=preheat_seconds,
        max_runtime_sec=max_runtime_sec,
        confirm_order=confirm_order,
    )


@mcp.tool()
async def damai_grab_multi(
    accounts: list[dict],
    item_id: str,
    price_index: int = 1,
    open_time: str = "",
    preheat_seconds: float = 30.0,
) -> dict[str, Any]:
    """多账号/多设备并发抢票（asyncio.gather）。

    Args:
        accounts: [{"device_id": "127.0.0.1:5555", "viewer_names": ["A"]}, ...]。
        item_id: 大麦 item id。
        price_index: 票档序号。
        open_time: 开票时间。
        preheat_seconds: 预热秒数。
    """
    import asyncio
    tasks = [
        _damai_grab(
            device_id=a["device_id"],
            item_id=item_id,
            price_index=price_index,
            viewer_names=a.get("viewer_names", []),
            ticket_num=a.get("ticket_num", 1),
            open_time=open_time,
            preheat_seconds=preheat_seconds,
        )
        for a in accounts
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"account_idx": i, "status": "error", "error": str(r)})
        else:
            r["account_idx"] = i
            out.append(r)
    return {"accounts": len(accounts), "results": out}


@mcp.tool()
async def ntp_sync(
    server: str = _DEFAULT_NTP_SERVER,
    timeout_sec: float = 5.0,
    device_id: str | None = None,
) -> dict[str, Any]:
    """NTP 时间同步 (推荐 ⭐⭐⭐⭐⭐)。

    多设备并行抢票时，确保所有设备时钟一致（精度 <100ms）。

    Args:
        server: NTP 服务器域名（默认 pool.ntp.org；国内推荐 cn.pool.ntp.org / ntp.aliyun.com）。
        timeout_sec: 超时秒数。
        device_id: 可选；同时拿设备的 Unix 时间戳做对比。
    """
    result = await _ntp_async_query(server, timeout_sec)
    payload = result.to_dict()
    if device_id is not None:
        device_unix = await _ntp_fetch_device_time(device_id)
        payload["device_unix"] = device_unix
        if device_unix is not None:
            payload["device_offset_ms"] = round(
                (result.server_unix - device_unix) * 1000, 2,
            )
    return payload


@mcp.tool()
async def damai_checklist_grab(
    device_id: str,
    item_id: str,
    open_time: str = "",
    price_index: int = 1,
    viewer_names: list[str] | None = None,
    ticket_num: int = 1,
    preheat_seconds: float = 30.0,
    ntp_server: str = "pool.ntp.org",
) -> dict[str, Any]:
    """抢票当天一键 checklist（推荐 ⭐⭐⭐⭐⭐）。

    一条命令跑完：NTP 时钟同步 → 设备检查 → 登录验证 → 详情页预热 → 倒计时 → 开票抢票。
    适合抢票当天 5 分钟前执行，会自动候场等开票。

    Args:
        device_id: 设备 ID。
        item_id: 大麦 item id。
        open_time: 开票时间 'YYYY-MM-DD HH:MM:SS'（空=立即抢）。
        price_index: 票档序号（1-based）。
        viewer_names: 观演人姓名列表。
        ticket_num: 张数。
        preheat_seconds: 开票前多少秒开始预热（默认 30）。
        ntp_server: NTP 服务器（默认 pool.ntp.org；国内用 cn.pool.ntp.org）。
    """
    async def _phase_cb(name: str) -> None:
        logger.info(f"[checklist] ▶ {name}")

    async def _progress_cb(seconds_left: float, elapsed_s: int) -> None:
        if seconds_left > 10:
            mins = int(seconds_left // 60)
            logger.info(f"[countdown] 开票 {mins} 分钟后，已候场 {elapsed_s}s")
        else:
            logger.info(f"[countdown] 开票 {seconds_left:.1f}s")

    res = await _damai_run_checklist(
        device_id=device_id,
        item_id=item_id,
        open_time=open_time,
        price_index=price_index,
        viewer_names=viewer_names or [],
        ticket_num=ticket_num,
        preheat_seconds=preheat_seconds,
        ntp_server=ntp_server,
        on_phase=_phase_cb,
        on_progress=_progress_cb,
    )
    return res.to_dict()


# ============================================================================
# L5 — Multi-app profile framework (大麦 / 猫眼 / 飞猪 / 自定义)
# ============================================================================

@mcp.tool()
async def list_app_profiles() -> dict[str, Any]:
    """列出所有已注册的 app profile（多网站抢票支持）。

    Returns:
        {"profiles": [{name, package_name, hints, step_count}]}
    """
    from .app.profile import load_profile
    names = _app_list_profiles()
    items = []
    for n in names:
        try:
            p = load_profile(n)
            items.append({
                "name": p.name,
                "package_name": p.package_name,
                "hints": p.hints,
                "step_count": len(p.steps),
                "viewer_picker": p.viewer_picker,
            })
        except Exception:
            continue
    return {"profiles": items, "count": len(items)}


@mcp.tool()
async def app_grab(
    device_id: str,
    profile_name: str,
    item_id: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """通用 app 抢票执行器（多网站支持 ⭐⭐⭐⭐⭐）。

    内置 profile：
        - damai (cn.damai)        大麦
        - maoyan (com.sankuai.movie) 猫眼
        - fliggy (com.taobao.trip)  飞猪

    Args:
        device_id: 设备 ID。
        profile_name: profile 名称（list_app_profiles 可查）。
        item_id: 商品 / 演出 id。
        options: 透传给 profile 的参数。例如
                 ``{"price_index": 1, "viewer_names": ["张三"], "ticket_num": 1}``。

    Returns:
        RunResult dict with per-step timing + status.
    """
    profile = _app_load_profile(profile_name)
    options = options or {}

    # Special dispatch: 大麦 handled via dedicated action
    if profile.name == "damai":
        from .damai.actions import damai_grab as _damai_grab_special
        grab = await _damai_grab_special(
            device_id=device_id,
            item_id=item_id,
            price_index=int(options.get("price_index", 1)),
            viewer_names=list(options.get("viewer_names", [])),
            ticket_num=int(options.get("ticket_num", 1)),
            open_time=options.get("open_time", ""),
            preheat_seconds=float(options.get("preheat_seconds", 0.0)),
            max_runtime_sec=float(options.get("max_runtime_sec", 60.0)),
        )
        return {
            "profile": profile.name,
            "package": profile.package_name,
            "item_id": item_id,
            "status": grab.get("status", "submitted"),
            "grab_result": grab,
            "dispatch": "damai_grab_special",
        }

    # Generic step runner for maoyan/fliggy/custom profiles
    # Hydrate runtime args from options
    for step in profile.steps:
        if step.action == "select_checkbox":
            label = options.get("viewer_label") or (
                options.get("viewer_names", [""])[0]
                if options.get("viewer_names") else ""
            )
            if label:
                step.args["label"] = label
        if step.action == "tap_index":
            if "index" not in step.args and "price_index" in options:
                step.args["index"] = int(options["price_index"]) - 1

    return (await _app_run_profile(profile, device_id, item_id, options)).to_dict()


# ============================================================================
# CLI entry
# ============================================================================

def main() -> None:
    """CLI entry point registered as `damai-mcp` script."""
    parser = argparse.ArgumentParser(prog="damai-mcp", description=__doc__)
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    parser.add_argument("--log-dir", default="./logs", help="日志目录")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_p = sub.add_parser("serve", help="启动 MCP server")
    serve_p.add_argument(
        "--transport", choices=["stdio", "streamable-http", "sse"],
        default="stdio",
    )
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)

    sub.add_parser("list-devices", help="列出连接的设备（一次性）")
    sub.add_parser("version", help="打印版本")

    # CLI: ntp-sync
    ntp_p = sub.add_parser(
        "ntp-sync",
        help="NTP 时钟同步 (打印 offset_ms)",
    )
    ntp_p.add_argument("--server", default="pool.ntp.org")
    ntp_p.add_argument("--timeout", type=float, default=5.0)
    ntp_p.add_argument("--device", default=None, help="同时校验设备时间")

    # CLI: list-profiles
    sub.add_parser("list-profiles", help="列出所有支持的 app profile")

    # CLI: app-grab
    app_p = sub.add_parser(
        "app-grab",
        help="通用多网站抢票执行器",
        description="用任意 profile 抢该网站的票。damai 走专用流程；其他走 step runner。",
    )
    app_p.add_argument("--device", required=True)
    app_p.add_argument("--profile", required=True, help="profile 名（先 list-profiles）")
    app_p.add_argument("--item-id", required=True)
    app_p.add_argument(
        "--option", action="append", default=[],
        help="profile 选项 (k=v，可多次)，如 --option price_index=1 --option viewer_names=张三",
    )

    # CLI: 抢票当天 checklist
    grab_p = sub.add_parser(
        "grab",
        help="抢票当天一键 checklist（推荐）",
        description=(
            "一条命令跑完：设备检查 → 登录验证 → 详情页预热 → 倒计时 → 开票抢票。"
            "适合开票前 5 分钟执行，自动候场等开票。"
        ),
    )
    grab_p.add_argument("--device", required=True, help="设备 ID，如 127.0.0.1:5555")
    grab_p.add_argument("--item-id", required=True, help="大麦 item id")
    grab_p.add_argument(
        "--open-time", default="",
        help="开票时间 'YYYY-MM-DD HH:MM:SS'，空=立即抢",
    )
    grab_p.add_argument("--price", type=int, default=1, help="票档序号（1-based）")
    grab_p.add_argument(
        "--viewer", action="append", default=[],
        help="观演人姓名（可多次 --viewer 张三）",
    )
    grab_p.add_argument("--num", type=int, default=1, help="张数")
    grab_p.add_argument(
        "--preheat", type=float, default=30.0,
        help="开票前预热秒数（默认 30）",
    )

    args = parser.parse_args()
    configure_logging(level=args.log_level, log_dir=Path(args.log_dir))

    if args.cmd == "serve":
        if args.transport != "stdio":
            logger.info(f"damai-mcp serving on http://{args.host}:{args.port} ({args.transport})")
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        mcp.run(transport=args.transport)
    elif args.cmd == "list-devices":
        import asyncio
        print(f"adb: {_which_adb()}")
        devices = asyncio.run(DeviceManager.shared().list_devices(refresh=True))
        for d in devices:
            tag = "EMU" if d.is_emulator else "DEVICE"
            print(f"  {d.device_id}\t{d.state}\t{d.model}\t{d.screen_size}\t{tag}")
    elif args.cmd == "list-profiles":
        import asyncio

        from .app.profile import load_profile
        names = _app_list_profiles()
        print(f"已注册 {len(names)} 个 profile:")
        for n in names:
            p = load_profile(n)
            steps = len(p.steps)
            hints = p.hints[:2]
            print(f"  - {n:10s} ({p.package_name:25s}) {steps} 步 hints={hints}")
    elif args.cmd == "version":
        from . import __version__
        print(f"damai-mcp {__version__}")
    elif args.cmd == "ntp-sync":
        import asyncio
        import json as _json
        result = asyncio.run(_ntp_async_query(args.server, args.timeout))
        print(_json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if args.device:
            device_unix = asyncio.run(_ntp_fetch_device_time(args.device))
            if device_unix is not None:
                delta_ms = (result.server_unix - device_unix) * 1000
                print(f"设备 {args.device} Unix={device_unix} 偏差 {delta_ms:+.2f}ms")
    elif args.cmd == "grab":
        import asyncio
        import json

        async def _phase_cb(name: str) -> None:
            print(f"  ▶ {name}", flush=True)

        async def _progress_cb(seconds_left: float, elapsed_s: int) -> None:
            if seconds_left > 60:
                print(f"  ⏱  开票还有 {int(seconds_left // 60)} 分钟", flush=True)
            elif seconds_left > 10:
                print(f"  ⏱  开票还有 {int(seconds_left)}s", flush=True)
            else:
                print(f"  🚀 开票 {seconds_left:.1f}s！", flush=True)

        logger.info(
            f"检查清单启动: device={args.device} item={args.item_id} "
            f"开票={args.open_time or 'now'} 票档={args.price}"
        )
        result = asyncio.run(_damai_run_checklist(
            device_id=args.device,
            item_id=args.item_id,
            open_time=args.open_time,
            price_index=args.price,
            viewer_names=args.viewer,
            ticket_num=args.num,
            preheat_seconds=args.preheat,
            on_phase=_phase_cb,
            on_progress=_progress_cb,
        ))
        print("\n" + "=" * 60)
        print(f"📋 结果: {result.status}")
        if result.error:
            print(f"❌ 错误: {result.error}")
        print("=" * 60)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif args.cmd == "app-grab":
        import asyncio
        import json
        options: dict[str, Any] = {}
        for kv in args.option:
            if "=" not in kv:
                print(f"⚠️  跳过非法 option {kv!r} (需要 k=v)")
                continue
            k, _, v = kv.partition("=")
            # try int
            try:
                v2: Any = int(v)
            except ValueError:
                v2 = v
            options[k] = v2
        logger.info(f"app-grab: profile={args.profile} item={args.item_id} options={options}")
        # Reuse the MCP tool implementation directly (avoids double-async wrapping)
        from .app.profile import load_profile as _load_profile
        from .damai.actions import damai_grab as _damai_grab_special
        profile = _load_profile(args.profile)
        if profile.name == "damai":
            grab = asyncio.run(_damai_grab_special(
                device_id=args.device,
                item_id=args.item_id,
                price_index=int(options.get("price_index", 1)),
                viewer_names=[options["viewer_label"]] if "viewer_label" in options else [],
                ticket_num=int(options.get("ticket_num", 1)),
                open_time=options.get("open_time", ""),
                preheat_seconds=float(options.get("preheat_seconds", 0.0)),
                max_runtime_sec=float(options.get("max_runtime_sec", 60.0)),
            ))
            result = {"profile": "damai", "status": grab.get("status"), "grab_result": grab}
        else:
            result = asyncio.run(_app_run_profile(profile, args.device, args.item_id, options)).to_dict()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
