"""Tests for UIElement model + parse_bounds."""
from __future__ import annotations

from damai_mcp.inspector.models import UIElement, parse_bounds


def test_parse_bounds_valid():
    assert parse_bounds("[100,200][300,400]") == (100, 200, 300, 400)


def test_parse_bounds_invalid():
    assert parse_bounds("garbage") == (0, 0, 0, 0)
    assert parse_bounds("") == (0, 0, 0, 0)


def test_ui_element_center():
    el = UIElement(tag="node", bounds=(10, 20, 110, 220))
    assert el.center == (60, 120)
    assert el.width == 100
    assert el.height == 200


def test_ui_element_visible_default():
    el = UIElement(tag="node", bounds=(0, 0, 100, 100), enabled=True)
    assert el.visible is True
    el2 = UIElement(tag="node", bounds=(0, 0, 0, 0), enabled=True)
    assert el2.visible is False
    el3 = UIElement(tag="node", bounds=(0, 0, 100, 100), enabled=False)
    assert el3.visible is False


def test_ui_element_to_dict_keys():
    el = UIElement(tag="node", text="OK", bounds=(0, 0, 10, 10))
    d = el.to_dict()
    assert "tag" in d
    assert "text" in d
    assert "center" in d
    assert d["center"] == [5, 5]


def test_ui_element_repr_includes_label():
    el = UIElement(tag="node", text="立即购买", bounds=(0, 0, 10, 10))
    r = repr(el)
    assert "立即购买" in r
    assert "node" in r
