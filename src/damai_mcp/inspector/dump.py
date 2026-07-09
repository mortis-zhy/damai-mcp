"""Parse the UIAutomator XML dump into UIElement objects."""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..device.adb import adb, shell
from ..utils.errors import ADBError
from ..utils.logging import logger
from .models import UIElement, parse_bounds

# Attributes we surface as first-class fields on UIElement
_NODE_FIELDS = (
    "text", "resource-id", "class", "content-desc",
    "clickable", "enabled", "selected", "checked",
    "password", "focused", "package",
)


async def dump_ui(device_id: str, *, compressed: bool = True) -> list[UIElement]:
    """Dump the current UI hierarchy as a flat list of UIElement.

    Returns a *flat* list (depth-first pre-order). Use the `parent` index if
    you need the tree structure (not exposed for simplicity).

    Implementation:
      1. `adb shell uiautomator dump /sdcard/window_dump.xml`
      2. `adb exec-out cat /sdcard/window_dump.xml` to read the XML
      3. lxml parse → walk all nodes
    """
    # 1. ask uiautomator to dump
    dump_cmd = "uiautomator dump --compressed" if compressed else "uiautomator dump"
    dump_out = await shell(dump_cmd, device_id=device_id, timeout=15, check=False)
    # uiautomator dump prints "UI hierchary dumped to: /sdcard/...xml" on stdout
    if not dump_out or "dumped" not in dump_out:
        raise ADBError(f"uiautomator dump 失败: {dump_out!r}")

    # 2. read the XML — try several known paths
    candidates = [
        "/sdcard/window_dump.xml",
        "/sdcard/dump.xml",
        "/data/local/tmp/ui_dump.xml",
        "/data/local/tmp/window_dump.xml",
    ]
    xml_text: str | None = None
    for path in candidates:
        out = await shell("cat", path, device_id=device_id, check=False, timeout=5)
        if out and "<node" in out:
            xml_text = out
            break
    if xml_text is None:
        # last resort: use adb pull
        result = await adb("exec-out", "cat", "/sdcard/window_dump.xml",
                           device_id=device_id, check=False, timeout=5)
        xml_text = result.stdout
    if not xml_text or "<node" not in xml_text:
        raise ADBError("uiautomator dump 未返回有效 XML")

    # 3. parse
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        logger.debug(f"XML 解析失败: {exc}; 前 200 字: {xml_text[:200]}")
        raise ADBError(f"UI XML 解析失败: {exc}") from exc

    elements: list[UIElement] = []
    for node in root.iter("node"):
        attrs = {f: node.get(f, "") for f in _NODE_FIELDS}
        try:
            el = UIElement(
                tag=node.tag,
                text=attrs["text"],
                resource_id=attrs["resource-id"],
                class_name=attrs["class"],
                content_desc=attrs["content-desc"],
                bounds=parse_bounds(node.get("bounds", "")),
                clickable=attrs["clickable"].lower() == "true",
                enabled=attrs["enabled"].lower() == "true",
                selected=attrs["selected"].lower() == "true",
                checked=attrs["checked"].lower() == "true",
                password=attrs["password"].lower() == "true",
                focused=attrs["focused"].lower() == "true",
                package=attrs["package"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"跳过坏节点 {node.get('bounds')}: {exc}")
            continue
        elements.append(el)
    return elements


async def dump_ui_to_file(device_id: str, save_path: str | Path) -> Path:
    """Dump UI and save raw XML to `save_path`. Useful for debugging."""
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    elements = await dump_ui(device_id)
    # Re-serialize a minimal XML for inspection
    from xml.etree import ElementTree as ET
    root = ET.Element("hierarchy")
    for el in elements:
        bounds_str = (
            f"[{el.bounds[0]},{el.bounds[1]}][{el.bounds[2]},{el.bounds[3]}]"
        )
        ET.SubElement(root, "node", attrib={
            "text": el.text,
            "resource-id": el.resource_id,
            "class": el.class_name,
            "bounds": bounds_str,
            "clickable": str(el.clickable).lower(),
        })
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


__all__ = ["dump_ui", "dump_ui_to_file"]
