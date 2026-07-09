"""大麦 app text/resource-id constants.

We do NOT hard-code these into the actions because 大麦 ships a new build every
week and selectors drift. Instead we treat them as defaults that callers can
override via the `selectors` parameter.

Verified against 大麦 app v8.4.5 (2026-06). Update via the
`damai_inspect_selectors` MCP tool when they drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DamaiSelectors:
    """All UI selectors used by 大麦 actions. Edit when 大麦 updates."""

    # Bottom tabs (inside main page)
    tab_home: str = "首页"
    tab_mine: str = "我的"

    # Concert detail page
    detail_buy_button: str = "立即购买"           # main buy CTA on detail page
    detail_buy_button_alt: str = "立即预订"       # alternate label
    detail_buy_button_alt2: str = "选座购买"     # "pick seat" variant

    # Price tier list inside the order sheet (¥XXX visible)
    # We locate by visible text; the tool matches with substring.

    # Viewer selector (观演人 list)
    viewer_checkbox_prefix: str = ""              # visual check state — checked by class change

    # Confirm / pay
    confirm_button: str = "确认订单"              # bottom confirm on order page
    pay_button: str = "立即支付"                  # bottom pay on pay page
    pay_success_indicator: str = "支付成功"       # text that appears after pay

    # Login state (search top bar, etc.)
    login_button: str = "登录/注册"

    # Slide captcha (大麦 slide puzzle)
    captcha_indicator: str = "请完成验证"          # if this text appears, captcha active
    captcha_swipe_to: str = "向右滑动滑块填充拼图"


@dataclass(slots=True)
class GrabConfig:
    """All knobs for one 抢票 run. Pass as kwargs to `damai_grab`."""

    device_id: str
    item_id: str                              # 大麦 item id, e.g. "1063631004645"
    price_index: int = 1                      # which tier (1-based) — ¥XXX displayed as text
    ticket_num: int = 1
    viewer_names: list[str] = field(default_factory=list)  # ["杨安琪"]
    open_time: str = ""                       # ISO "YYYY-MM-DD HH:MM:SS"; empty = immediate
    preheat_seconds: float = 30.0             # open detail page this early
    max_runtime_sec: float = 600.0            # hard stop
    poll_interval_ms: int = 150               # how often to re-dump UI while waiting
    selectors: DamaiSelectors = field(default_factory=DamaiSelectors)


__all__ = ["DamaiSelectors", "GrabConfig"]
