"""Find UIElement by various selectors + wait helpers."""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from typing import Any

from ..utils.errors import UIElementNotFoundError
from .dump import dump_ui
from .models import UIElement

# ---- single find ------------------------------------------------------------

async def find_by_text(
    device_id: str,
    text: str,
    *,
    exact: bool = True,
    clickable_only: bool = False,
    timeout: float = 5.0,
    poll_interval: float = 0.3,
) -> UIElement:
    """Find a UIElement whose text/content-desc/resource-id contains `text`.

    `exact=False` does substring match; `exact=True` (default) is whole-string
    equality. Returns first match or raises UIElementNotFoundError.
    """
    return await _wait_for(
        device_id,
        predicate=lambda e: _matches_text(e, text, exact=exact),
        timeout=timeout,
        poll_interval=poll_interval,
        description=f"text={text!r}",
        extra_filter=lambda e: (not clickable_only) or e.clickable,
    )


async def find_by_resource_id(
    device_id: str,
    resource_id: str,
    *,
    exact: bool = True,
    timeout: float = 5.0,
    poll_interval: float = 0.3,
) -> UIElement:
    """Find by `resource-id` (full or suffix)."""
    return await _wait_for(
        device_id,
        predicate=lambda e: _matches_rid(e, resource_id, exact=exact),
        timeout=timeout,
        poll_interval=poll_interval,
        description=f"resource-id={resource_id!r}",
    )


async def find_by_xpath(
    device_id: str,
    xpath: str,
    *,
    timeout: float = 5.0,
    poll_interval: float = 0.3,
) -> UIElement:
    """Find via lxml XPath over the UI tree.

    Variables: `text`, `resource-id`, `class`, `content-desc`, `package`.
    Example: `//node[@text='立即购买' and @clickable='true']`
    """
    def predicate(elements: list[UIElement]) -> UIElement | None:
        # Re-build a minimal lxml tree from flat UIElement list.
        from xml.etree import ElementTree as ET

        from lxml import etree
        root = ET.Element("hierarchy")
        for el in elements:
            ET.SubElement(root, "node", attrib={
                "text": el.text, "resource-id": el.resource_id,
                "class": el.class_name, "content-desc": el.content_desc,
                "bounds": _bounds_str(el.bounds),
                "clickable": str(el.clickable).lower(),
                "enabled": str(el.enabled).lower(),
            })
        try:
            hits = etree.ElementTree(root).xpath(xpath)
        except etree.XPathEvalError as exc:
            raise UIElementNotFoundError(f"XPath 错误: {exc}") from exc
        if not hits:
            return None
        # Map back to UIElement by bounds (cheap and unique enough)
        bounds = parse_bounds_str(hits[0].get("bounds", ""))
        for el in elements:
            if el.bounds == bounds:
                return el
        return None

    return await _wait_for(
        device_id,
        predicate=predicate,
        timeout=timeout,
        poll_interval=poll_interval,
        description=f"xpath={xpath!r}",
    )


async def wait_for_text(
    device_id: str,
    text: str,
    *,
    exact: bool = True,
    timeout: float = 5.0,
    poll_interval: float = 0.3,
) -> UIElement:
    return await find_by_text(
        device_id, text, exact=exact, timeout=timeout, poll_interval=poll_interval
    )


async def wait_for_element(
    device_id: str,
    selector: str,
    *,
    timeout: float = 5.0,
    poll_interval: float = 0.3,
) -> UIElement:
    """Convenience: prefix-based selector dispatch.

    Supported prefixes:
        `text=...`           → find_by_text
        `resource-id=...`    → find_by_resource_id
        `xpath=...`          → find_by_xpath
        bare value           → treated as text
    """
    if selector.startswith("text="):
        return await find_by_text(
            device_id, selector[5:], timeout=timeout, poll_interval=poll_interval,
        )
    if selector.startswith("resource-id="):
        return await find_by_resource_id(
            device_id, selector[12:], timeout=timeout, poll_interval=poll_interval,
        )
    if selector.startswith("xpath="):
        return await find_by_xpath(
            device_id, selector[6:], timeout=timeout, poll_interval=poll_interval,
        )
    return await find_by_text(device_id, selector, timeout=timeout, poll_interval=poll_interval)


async def assert_text(
    device_id: str, text: str, *, exact: bool = True, timeout: float = 3.0
) -> bool:
    """Returns True if text appears within timeout, False otherwise."""
    try:
        await find_by_text(device_id, text, exact=exact, timeout=timeout)
        return True
    except UIElementNotFoundError:
        return False


# ---- internal ---------------------------------------------------------------

def _matches_text(el: UIElement, needle: str, *, exact: bool) -> bool:
    if not needle:
        return False
    candidates = (el.text, el.content_desc)
    if exact:
        return any(c == needle for c in candidates)
    return any(needle in c for c in candidates if c)


def _matches_rid(el: UIElement, needle: str, *, exact: bool) -> bool:
    if not el.resource_id:
        return False
    if exact:
        return el.resource_id == needle
    return el.resource_id.endswith(needle) or needle in el.resource_id


def _bounds_str(b: tuple[int, int, int, int]) -> str:
    return f"[{b[0]},{b[1]}][{b[2]},{b[3]}]"


def parse_bounds_str(s: str) -> tuple[int, int, int, int]:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", s)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0, 0)


async def _wait_for(
    device_id: str,
    *,
    predicate: Callable[[list[UIElement]], UIElement | None] | Callable[[UIElement], bool],
    timeout: float,
    poll_interval: float,
    description: str,
    extra_filter: Callable[[UIElement], bool] | None = None,
) -> UIElement:
    """Generic waiter.

    `predicate` is either a function over a UIElement (predicate-style) or a
    function over the entire elements list (xpath-style).
    """
    deadline = time.monotonic() + timeout
    last_dump_count = -1
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            elements = await dump_ui(device_id)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            await asyncio.sleep(poll_interval)
            continue
        last_dump_count = len(elements)

        if extra_filter:
            elements = [e for e in elements if extra_filter(e)]

        try:
            if _is_list_predicate(predicate):
                result = predicate(elements)  # type: ignore[arg-type]
            else:
                result = next(
                    (e for e in elements if predicate(e)),  # type: ignore[arg-type]
                    None,
                )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            await asyncio.sleep(poll_interval)
            continue

        if result is not None and result.visible:
            return result
        await asyncio.sleep(poll_interval)

    msg = f"等待 {description} 超时（{timeout}s，dump 节点数 {last_dump_count}）"
    if last_error:
        msg += f"，最后错误: {last_error}"
    raise UIElementNotFoundError(msg)


def _is_list_predicate(p: Callable[..., Any]) -> bool:
    """Heuristic: list-predicate takes a single list param; element-predicate takes UIElement."""
    # The element predicate is called with one positional arg in next(generator).
    # This isn't perfect; we use a parameter-name hint instead.
    import inspect
    try:
        sig = inspect.signature(p)
        for p_name in sig.parameters.values():
            ann = str(p_name.annotation).lower()
            if "list" in ann or "elements" in ann:
                return True
        return False
    except (TypeError, ValueError):
        return False


__all__ = [
    "find_by_text",
    "find_by_resource_id",
    "find_by_xpath",
    "wait_for_text",
    "wait_for_element",
    "assert_text",
]
