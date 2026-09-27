"""Pure-function search over :class:`UIElement` lists.

Lives next to :mod:`ui_cache` so the cache can run searches without
importing :mod:`inspector.find` (which has the heavy IO functions).
"""
from __future__ import annotations

from typing import Any

from ..inspector.models import UIElement


def _matches_text(el: UIElement, text: str, exact: bool) -> bool:
    if el.text is None:
        return False
    return el.text == text if exact else text in el.text


def _matches_resource_id(el: UIElement, resource_id: str, exact: bool) -> bool:
    if el.resource_id is None:
        return False
    if exact:
        return el.resource_id == resource_id
    return el.resource_id.endswith(resource_id)


def search_elements(
    elements: list[UIElement],
    *,
    text: str | None = None,
    resource_id: str | None = None,
    xpath: str | None = None,
    exact: bool = True,
) -> UIElement | None:
    """Return the first matching :class:`UIElement` or ``None``.

    At least one of ``text``, ``resource_id``, ``xpath`` must be provided.
    """
    if not any([text, resource_id, xpath]):
        raise ValueError("must supply one of text/resource_id/xpath")

    matches: list[UIElement] = []
    if xpath is not None:
        from lxml import etree  # type: ignore[import-untyped]
        tree = etree.ElementTree(etree.fromstring(_pack(elements)))
        hits = tree.xpath(xpath)
        matches = [_unpack(h) for h in hits]
    else:
        for el in elements:
            if text is not None and not _matches_text(el, text, exact):
                continue
            if resource_id is not None and not _matches_resource_id(el, resource_id, exact):
                continue
            matches.append(el)
    return matches[0] if matches else None


# ---- element <-> xml pack/unpack (lightweight) -------------------------

_PACK_FIELDS = ("text", "resource-id", "class", "package", "content-desc",
                "bounds", "clickable", "enabled")


def _pack(elements: list[UIElement]) -> bytes:
    """Serialize elements to a tiny XML tree for lxml.xpath."""
    import xml.etree.ElementTree as ET
    root = ET.Element("hierarchy")
    for el in elements:
        node = ET.SubElement(root, "node")
        for f in _PACK_FIELDS:
            attr_name = f.replace("-", "_")
            v: Any = getattr(el, attr_name, None)
            if v is None:
                continue
            if attr_name == "bounds" and isinstance(v, tuple):
                v = f"[{v[0]},{v[1]}][{v[2]},{v[3]}]"
            node.set(f, str(v))
    return ET.tostring(root, encoding="utf-8")


def _unpack(node) -> UIElement:  # type: ignore[no-untyped-def]
    from ..inspector.models import parse_bounds
    bounds_attr = node.get("bounds")
    return UIElement(
        tag="node",
        text=node.get("text") or "",
        resource_id=node.get("resource-id") or "",
        class_name=node.get("class") or "",
        content_desc=node.get("content-desc") or "",
        bounds=parse_bounds(bounds_attr) if bounds_attr else (0, 0, 0, 0),
        clickable=node.get("clickable", "").lower() == "true",
        enabled=node.get("enabled", "").lower() == "true",
        package=node.get("package") or "",
    )
