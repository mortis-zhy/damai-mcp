"""大麦-specific business actions: login check, open concert, select price/viewer, grab."""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from typing import Any

from ..actions.actions import screenshot, tap, wait_ms
from ..device.adb import shell
from ..inspector.find import (
    assert_text,
    wait_for_element,
)
from ..inspector.models import UIElement
from ..utils.errors import (
    AppNotRunningError,
    DamaiGrabFailedError,
    DamaiLoginExpiredError,
    UIElementNotFoundError,
)
from ..utils.logging import logger
from .selectors import DamaiSelectors

DAMAI_PACKAGE = "cn.damai"
DAMAI_MAIN_ACTIVITY = "cn.damai.homepage.MainActivity"


# ---- helpers ----------------------------------------------------------------

async def _is_damai_foreground(device_id: str) -> bool:
    """Check current top activity — used to detect app crashes / foreground loss."""
    out = await shell(
        "dumpsys", "activity", "activities",
        device_id=device_id, timeout=5, check=False,
    )
    return DAMAI_PACKAGE in out


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


async def _wait_until(target_ts: float, *, poll_ms: int = 200) -> None:
    """Sleep until target monotonic ts, with fine-grained polling."""
    while True:
        now = time.time()
        remaining = target_ts - now
        if remaining <= 0:
            return
        # For sub-100ms waits, busy-loop; for longer, sleep chunked
        if remaining < 0.2:
            await asyncio.sleep(max(remaining, 0))
            return
        await asyncio.sleep(min(remaining - 0.1, poll_ms / 1000))


def _is_in_viewer_name_list(text: str, viewers: list[str]) -> bool:
    """Match viewer display name in 大麦 UI — may include "(实名)" suffix."""
    t = text.strip()
    for v in viewers:
        if v in t or t.startswith(v):
            return True
    return False


# ---- 1. login check ---------------------------------------------------------

async def damai_login_check(device_id: str, *, timeout: float = 3.0) -> dict[str, Any]:
    """Verify 大麦 app is foreground and user is logged in.

    Returns: {"logged_in": bool, "foreground": bool, "user_hint": str|None}
    Raises: AppNotRunningError if 大麦 isn't in foreground.
    """
    if not await _is_damai_foreground(device_id):
        raise AppNotRunningError(
            f"大麦 ({DAMAI_PACKAGE}) 不在前台，请先打开 APP 并登录。"
        )
    # Logged-in indicator: "我的" tab shows username / 我的订单 visible
    # Logged-out indicator: 登录/注册 button visible
    login_btn = await assert_text(device_id, "登录/注册", timeout=timeout)
    if login_btn:
        return {"logged_in": False, "foreground": True, "user_hint": None}
    return {"logged_in": True, "foreground": True, "user_hint": None}


# ---- 2. open concert --------------------------------------------------------

async def damai_open_concert(device_id: str, item_id: str, *,
                             selectors: DamaiSelectors | None = None) -> dict[str, Any]:
    """Navigate to a concert detail page using its item_id.

    Uses the deep-link scheme `damai://item?id=...` which the app handles.
    Falls back to web URL via adb am start.

    Returns: {"item_id": str, "loaded": bool, "elapsed_ms": int}
    """
    t0 = time.time()
    selectors = selectors or DamaiSelectors()
    # Scheme 1: app deep link
    await shell(
        "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", f"damai://item?id={item_id}",
        device_id=device_id, check=False, timeout=10,
    )
    await wait_ms(1500)
    if not await _is_damai_foreground(device_id):
        # Scheme 2: web URL → forced open in app
        await shell(
            "am", "start", "-W", "-a", "android.intent.action.VIEW",
            "-d", f"https://m.damai.cn/shows/item.html?itemId={item_id}",
            device_id=device_id, check=False, timeout=10,
        )
        await wait_ms(2000)
    # Wait for buy button to appear (means page is loaded)
    try:
        await wait_for_element(
            device_id, f"text={selectors.detail_buy_button}", timeout=8.0
        )
        loaded = True
    except UIElementNotFoundError:
        loaded = False
    return {
        "item_id": item_id,
        "loaded": loaded,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


# ---- 3. select price --------------------------------------------------------

async def damai_select_price(
    device_id: str,
    price_index: int,
    *,
    selectors: DamaiSelectors | None = None,
    timeout: float = 4.0,
) -> UIElement:
    """Pick the Nth price tier from the price picker.

    Strategy: dump UI, find elements whose text matches `¥<number>`, return
    the (price_index)-th one. Click on its center.
    """
    selectors = selectors or DamaiSelectors()
    # Make sure price picker is open
    try:
        await wait_for_element(
            device_id, "text=¥", timeout=timeout, poll_interval=0.2
        )
    except UIElementNotFoundError as exc:
        raise DamaiGrabFailedError(f"价格表未弹出: {exc}") from exc

    # Dump and find all ¥xxx elements, sort top-to-bottom
    from ..inspector.dump import dump_ui
    elements = await dump_ui(device_id)
    price_els = [
        e for e in elements
        if e.text and re.match(r"^¥\d+(\.\d+)?$", e.text.strip())
        and e.visible
    ]
    if not price_els:
        raise DamaiGrabFailedError("未找到任何 ¥xxx 价格元素")
    # Sort by Y, then X (top-down, left-right)
    price_els.sort(key=lambda e: (e.bounds[1], e.bounds[0]))
    if price_index < 1 or price_index > len(price_els):
        raise DamaiGrabFailedError(
            f"price_index={price_index} 超出范围 (1..{len(price_els)})"
        )
    target = price_els[price_index - 1]
    await tap(device_id, *target.center)
    await wait_ms(400)
    return target


# ---- 4. select viewer -------------------------------------------------------

async def damai_select_viewers(
    device_id: str,
    viewer_names: list[str],
    *,
    timeout: float = 4.0,
) -> list[UIElement]:
    """Click the checkbox next to each named viewer. Returns clicked elements."""
    from ..inspector.dump import dump_ui
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            elements = await dump_ui(device_id)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            await asyncio.sleep(0.3)
            continue

        clicked: list[UIElement] = []
        for name in viewer_names:
            # Find by visible name (may be wrapped)
            target = next(
                (e for e in elements if e.visible and _is_in_viewer_name_list(e.text, [name])),
                None,
            )
            if target is None:
                continue
            # Click the element itself (大麦 makes the name row clickable)
            await tap(device_id, *target.center)
            clicked.append(target)
            await wait_ms(150)
        if len(clicked) == len(viewer_names):
            return clicked
        await asyncio.sleep(0.3)

    raise DamaiGrabFailedError(
        f"选观演人超时（{timeout}s）: 已点 {len(clicked)}/{len(viewer_names)}，最后错误: {last_err}"
    )


# ---- 5. confirm + pay -------------------------------------------------------

async def damai_confirm_order(
    device_id: str,
    *,
    selectors: DamaiSelectors | None = None,
    timeout: float = 5.0,
) -> UIElement:
    """Tap the 确认订单 button. Returns the tapped element."""
    selectors = selectors or DamaiSelectors()
    btn = await wait_for_element(
        device_id, f"text={selectors.confirm_button}", timeout=timeout
    )
    await tap(device_id, *btn.center)
    return btn


async def damai_pay(
    device_id: str,
    *,
    selectors: DamaiSelectors | None = None,
    timeout: float = 5.0,
) -> UIElement:
    """Tap 立即支付 — returns the tapped element. Caller must complete payment in APP."""
    selectors = selectors or DamaiSelectors()
    btn = await wait_for_element(
        device_id, f"text={selectors.pay_button}", timeout=timeout
    )
    await tap(device_id, *btn.center)
    return btn


# ---- 6. one-shot grab -------------------------------------------------------

async def damai_grab(
    device_id: str,
    item_id: str,
    price_index: int = 1,
    viewer_names: list[str] | None = None,
    ticket_num: int = 1,
    open_time: str = "",
    *,
    selectors: DamaiSelectors | None = None,
    preheat_seconds: float = 30.0,
    max_runtime_sec: float = 600.0,
    poll_interval_ms: int = 150,
) -> dict[str, Any]:
    """One-shot 抢票: preheat → wait for open → buy → confirm.

    Returns: {
        "status": "submitted" | "failed",
        "elapsed_ms": int,
        "screenshots": [paths...],
        "error": str | None,
    }
    """
    selectors = selectors or DamaiSelectors()
    viewer_names = viewer_names or []
    t_start = time.time()

    shots_dir = _shots_dir()
    log_paths: list[str] = []

    try:
        # 1. Verify login
        login = await damai_login_check(device_id)
        if not login["logged_in"]:
            raise DamaiLoginExpiredError(
                "大麦未登录，请先在大麦 APP 里扫码登录。"
            )

        # 2. Open concert
        open_res = await damai_open_concert(device_id, item_id, selectors=selectors)
        if not open_res["loaded"]:
            shot = str(shots_dir / f"open_fail_{int(time.time())}.png")
            await screenshot(device_id, shot)
            log_paths.append(shot)
            raise DamaiGrabFailedError(
                f"详情页加载失败（{open_res['elapsed_ms']}ms），截图: {shot}"
            )

        # 3. Compute target timestamp
        if open_time:
            target_ts = _parse_iso(open_time).timestamp()
        else:
            target_ts = time.time()

        # 4. Preheat — done by `damai_open_concert` (already at detail page).
        #    If preheat > 0, wait until `target_ts - preheat_seconds` before
        #    tapping the buy button.
        preheat_until = max(target_ts - preheat_seconds, time.time())
        if preheat_until > time.time():
            await _wait_until(preheat_until, poll_ms=poll_interval_ms)
            logger.info(f"预热完成，等待开票: {target_ts - time.time():.1f}s")

        # 5. Wait for open time
        if time.time() < target_ts:
            await _wait_until(target_ts, poll_ms=poll_interval_ms)
            logger.success(f"⏰ 开票！开始抢票 ({viewer_names}, 票档 #{price_index})")

        # 6. Tap buy button (try all known variants)
        buy_btn = None
        for label in (selectors.detail_buy_button,
                      selectors.detail_buy_button_alt,
                      selectors.detail_buy_button_alt2):
            try:
                buy_btn = await wait_for_element(
                    device_id, f"text={label}", timeout=1.5
                )
                break
            except UIElementNotFoundError:
                continue
        if buy_btn is None:
            shot = str(shots_dir / f"no_buy_btn_{int(time.time())}.png")
            await screenshot(device_id, shot)
            log_paths.append(shot)
            raise DamaiGrabFailedError(
                f"找不到立即购买按钮，截图: {shot}"
            )
        await tap(device_id, *buy_btn.center)

        # 7. Pick price tier
        await damai_select_price(device_id, price_index, selectors=selectors)

        # 8. Select viewers
        if viewer_names:
            await damai_select_viewers(device_id, viewer_names)

        # 9. Confirm order
        await damai_confirm_order(device_id, selectors=selectors)

        # 10. Pay button (caller will pay in APP)
        try:
            pay_btn = await damai_pay(device_id, selectors=selectors, timeout=3.0)
        except UIElementNotFoundError:
            pay_btn = None  # May need extra verification step

        shot = str(shots_dir / f"grab_done_{int(time.time())}.png")
        await screenshot(device_id, shot)
        log_paths.append(shot)

        elapsed = int((time.time() - t_start) * 1000)
        return {
            "status": "submitted",
            "elapsed_ms": elapsed,
            "item_id": item_id,
            "price_index": price_index,
            "viewer_names": viewer_names,
            "pay_btn_found": pay_btn is not None,
            "screenshots": log_paths,
            "error": None,
        }

    except (DamaiGrabFailedError, DamaiLoginExpiredError) as exc:
        elapsed = int((time.time() - t_start) * 1000)
        shot = str(shots_dir / f"grab_fail_{int(time.time())}.png")
        try:
            await screenshot(device_id, shot)
            log_paths.append(shot)
        except Exception:  # noqa: BLE001
            pass
        return {
            "status": "failed",
            "elapsed_ms": elapsed,
            "screenshots": log_paths,
            "error": str(exc),
        }


def _shots_dir() -> Any:
    """Path to debug screenshots."""
    from pathlib import Path
    p = Path("./damai_shots")
    p.mkdir(exist_ok=True)
    return p


__all__ = [
    "damai_login_check",
    "damai_open_concert",
    "damai_select_price",
    "damai_select_viewers",
    "damai_confirm_order",
    "damai_pay",
    "damai_grab",
    "DAMAI_PACKAGE",
    "DAMAI_MAIN_ACTIVITY",
]
