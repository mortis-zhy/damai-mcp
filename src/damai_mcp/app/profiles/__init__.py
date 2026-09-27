"""Built-in app profiles.

Loaded into the registry by :func:`damai_mcp.app.profile.load_profile`
on demand, so the registry starts empty.
"""
from __future__ import annotations

from .damai import DAMAI_PROFILE
from .fliggy import FLIGGY_PROFILE
from .maoyan import MAOYAN_PROFILE

__all__ = ["DAMAI_PROFILE", "MAOYAN_PROFILE", "FLIGGY_PROFILE", "_register_builtins"]


def _register_builtins(registry: dict) -> None:
    """Register all built-in profiles into ``registry``."""
    for profile in (DAMAI_PROFILE, MAOYAN_PROFILE, FLIGGY_PROFILE):
        if profile.name in registry:
            continue
        registry[profile.name] = profile
