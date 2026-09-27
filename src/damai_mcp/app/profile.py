"""Multi-app profile framework.

A profile describes how to drive one specific app for ticket grabbing. Each
profile is a sequence of :class:`Step` objects that the runner interprets.
The buyer (or AI agent) supplies ``device_id``, ``item_id`` and any
profile-specific options — never raw selectors.

Profiles live in :mod:`damai_mcp.app.profiles` and can be loaded via
:func:`load_profile(name)`.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..utils.logging import logger

# Action types the runner knows how to execute.
Action = Literal[
    "open_detail",         # launch the app + nav to item detail
    "wait_text",           # wait for text to appear
    "tap_text",            # find text and tap
    "tap_index",           # tap the Nth matching text
    "select_checkbox",     # toggle a checkbox by adjacent text label
    "check_text",          # assert text appears (does not tap)
    "sleep",               # straight sleep, seconds
    "screenshot",          # take screenshot to file/return_base64
]

StepArg = dict[str, Any]


@dataclass
class Step:
    """A single UI operation in a grab pipeline."""

    name: str
    action: Action
    args: StepArg = field(default_factory=dict)
    timeout_sec: float = 5.0
    continue_on_fail: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "action": self.action,
            "args": self.args,
            "timeout_sec": self.timeout_sec,
            "continue_on_fail": self.continue_on_fail,
        }


@dataclass
class AppProfile:
    """How to grab tickets on a specific app.

    Attributes:
        name: short identifier e.g. ``damai``, ``maoyan``.
        package_name: Android package id, e.g. ``cn.damai``.
        deep_link_template: optional URL template, ``{item_id}`` is replaced.
        steps: ordered actions executed after open_detail. Each step receives
            the running context (device_id, item_id, options).
        viewer_picker: if the app supports multiple viewers (实名制), the
            text alias of the list — filled by ``select_viewers`` later.
        hints: free-form strings the agent can use (e.g. ``"amap_disabled"``).
    """

    name: str
    package_name: str
    deep_link_template: str | None = None
    steps: list[Step] = field(default_factory=list)
    viewer_picker: str | None = None
    hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "package_name": self.package_name,
            "deep_link_template": self.deep_link_template,
            "steps": [s.to_dict() for s in self.steps],
            "viewer_picker": self.viewer_picker,
            "hints": self.hints,
        }


# -------- registry ---------------------------------------------------------

_PROFILES: dict[str, AppProfile] = {}


def register_profile(profile: AppProfile, *, override: bool = False) -> None:
    """Register a profile into the in-memory registry.

    Set ``override=True`` to allow replacing a built-in profile (useful in
    tests and when loading user profiles from disk).
    """
    if profile.name in _PROFILES and not override:
        raise ValueError(f"profile {profile.name!r} already registered; pass override=True")
    _PROFILES[profile.name] = profile
    logger.debug(f"registered profile {profile.name!r} ({profile.package_name})")


def get_profile(name: str) -> AppProfile:
    if name not in _PROFILES:
        raise KeyError(
            f"profile {name!r} not found; available: {sorted(_PROFILES)}"
        )
    return _PROFILES[name]


def list_profiles() -> list[str]:
    return sorted(_PROFILES)


def load_profile(name: str) -> AppProfile:
    """Return a profile by name; loads built-ins lazily on first call."""
    if not _PROFILES:
        from .profiles import _register_builtins
        _register_builtins(_PROFILES)
    return get_profile(name)


# Eager registration: load built-ins once when the module is imported so
# list_app_profiles() always returns the canonical set.
def _load_builtins_once() -> None:
    """Idempotent: import the built-in profiles into the registry."""
    if _PROFILES:
        return
    try:
        from .profiles import _register_builtins
        _register_builtins(_PROFILES)
    except Exception:  # noqa: BLE001 — we just want a graceful fallback
        # The built-in profiles are optional; if they fail to import we leave
        # the registry empty (it can still be populated via load_profile_file).
        import logging
        logging.getLogger(__name__).exception("failed to register built-in profiles")


_load_builtins_once()


# -------- profile loading from disk ---------------------------------------

def load_profile_file(path: str | Path) -> AppProfile:
    """Load a profile from a JSON file on disk and register it.

    The file shape matches :meth:`AppProfile.to_dict`.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    steps = [
        Step(
            name=s["name"],
            action=s["action"],  # type: ignore[arg-type]
            args=s.get("args", {}),
            timeout_sec=s.get("timeout_sec", 5.0),
            continue_on_fail=s.get("continue_on_fail", False),
        )
        for s in data.pop("steps", [])
    ]
    profile = AppProfile(
        steps=steps,
        **data,
    )
    register_profile(profile, override=True)
    return profile


# -------- type for custom step callbacks ----------------------------------

# Async callback for a custom step. Receives (step, ctx) and returns dict.
CustomStepHandler = Callable[["Step", "RunContext"], Awaitable[dict[str, Any] | None]]


@dataclass
class RunContext:
    """Shared state passed to every step during a run."""

    device_id: str
    item_id: str
    options: dict[str, Any] = field(default_factory=dict)
    last_result: dict[str, Any] | None = None
