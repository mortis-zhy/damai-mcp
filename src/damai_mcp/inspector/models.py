"""UI element model + XPath-like selectors for Android UIAutomator XML.

We use a minimal lxml-based parser instead of pulling in `uiautomator2`
because (a) MCP needs only read access to the XML and (b) uiautomator2 also
runs an HTTP server inside the device, which is heavier than necessary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class UIElement:
    """One node in the UIAutomator dump."""

    tag: str
    text: str = ""
    resource_id: str = ""
    class_name: str = ""
    content_desc: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)  # x1, y1, x2, y2
    clickable: bool = False
    enabled: bool = True
    selected: bool = False
    checked: bool = False
    password: bool = False
    focused: bool = False
    package: str = ""
    attrs: dict[str, str] | None = None

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def visible(self) -> bool:
        x1, y1, x2, y2 = self.bounds
        return self.enabled and (x2 > x1) and (y2 > y1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "text": self.text,
            "resource_id": self.resource_id,
            "class_name": self.class_name,
            "content_desc": self.content_desc,
            "bounds": list(self.bounds),
            "center": list(self.center),
            "clickable": self.clickable,
            "enabled": self.enabled,
            "selected": self.selected,
            "checked": self.checked,
            "package": self.package,
        }

    def __repr__(self) -> str:
        label = self.text or self.content_desc or self.resource_id or self.class_name
        return f"<UIElement {self.tag} {label!r} @ {self.center}>"


def parse_bounds(bounds_attr: str) -> tuple[int, int, int, int]:
    """Parse bounds string '[x1,y1][x2,y2]'."""
    import re
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_attr)
    if not m:
        return (0, 0, 0, 0)
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


__all__ = ["UIElement", "parse_bounds"]
