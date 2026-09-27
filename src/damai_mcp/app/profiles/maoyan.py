"""猫眼 (com.sankuai.movie) profile.

Cat's Eye uses a fairly standard merchant flow:
    详情页 → "立即购买" → 选场次/票价 → 实名观演人 → 确认
"""
from __future__ import annotations

from ..profile import AppProfile, Step

MAOYAN_PROFILE = AppProfile(
    name="maoyan",
    package_name="com.sankuai.movie",
    deep_link_template="maoyan://movie/{item_id}",
    hints=[
        "Standard sold-out guard: button shows '已售罄'",
        "Price tier is a horizontal scroll; pick the 1st 'available' badge",
        "Viewer picker uses '实名观演人' title",
    ],
    viewer_picker="实名观演人",
    steps=[
        Step(
            name="open_detail",
            action="open_detail",
            args={},
            timeout_sec=15.0,
        ),
        Step(
            name="wait_buy_visible",
            action="wait_text",
            args={"text": "立即购买", "exact": False},
            timeout_sec=30.0,
        ),
        Step(
            name="tap_buy",
            action="tap_text",
            args={"text": "立即购买", "exact": False},
            timeout_sec=5.0,
        ),
        Step(
            name="select_price",
            action="tap_index",
            args={"text": "¥", "index": 0},
            timeout_sec=5.0,
        ),
        Step(
            name="tick_viewer",
            action="select_checkbox",
            args={"label": ""},  # set from options at runtime
            timeout_sec=5.0,
            continue_on_fail=True,  # optional step
        ),
        Step(
            name="confirm_order",
            action="tap_text",
            args={"text": "确认订单", "exact": False},
            timeout_sec=8.0,
        ),
    ],
)
