"""飞猪 (com.taobao.trip) profile.

Flīggy's show grab flow:
    场次列表 → 选场次 → 选票价 → 实名 → 提交订单
"""
from __future__ import annotations

from ..profile import AppProfile, Step

FLIGGY_PROFILE = AppProfile(
    name="fliggy",
    package_name="com.taobao.trip",
    deep_link_template="fliggy://item/{item_id}",
    hints=[
        "Sold-out badge: '已售完'",
        "Show selection uses card list (CarouselView)",
    ],
    viewer_picker="出行人",
    steps=[
        Step(
            name="open_detail",
            action="open_detail",
            args={},
            timeout_sec=15.0,
        ),
        Step(
            name="wait_session",
            action="wait_text",
            args={"text": "场次", "exact": False},
            timeout_sec=30.0,
        ),
        Step(
            name="tap_price",
            action="tap_index",
            args={"text": "¥", "index": 0},
            timeout_sec=5.0,
        ),
        Step(
            name="tick_traveler",
            action="select_checkbox",
            args={"label": ""},  # set at runtime from options
            timeout_sec=5.0,
            continue_on_fail=True,
        ),
        Step(
            name="confirm_order",
            action="tap_text",
            args={"text": "提交订单", "exact": False},
            timeout_sec=8.0,
        ),
    ],
)
