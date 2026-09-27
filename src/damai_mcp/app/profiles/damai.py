"""大麦 (cn.damai) profile.

Triggered via the existing :func:`damai_mcp.damai.actions.damai_grab` rather
than the generic step runner — 大麦 has the most complex UI (实名制, J2C
shell, APM) so wrapping it as a profile would lose fidelity.

This profile is therefore mostly declarative: the runner looks up this
profile and dispatches to ``damai_grab`` when ``kind=='damai_special'``.
"""
from __future__ import annotations

from ..profile import AppProfile, Step

DAMAI_PROFILE = AppProfile(
    name="damai",
    package_name="cn.damai",
    deep_link_template="damai://item/{item_id}",
    hints=[
        "Uses J2C (Aliyun obfuscation) shell, native APM protection",
        "Requires login (saved by damai_login_check)",
        "Picker requires real-name viewer name",
    ],
    viewer_picker="观演人",
    steps=[
        # Step list is declarative; the runner dispatches via a special branch
        # in app.run_profile when the profile name == 'damai'.
        Step(
            name="delegate_to_damai_grab",
            action="sleep",  # placeholder, never executed
            args={"seconds": 0.0},
        ),
    ],
)
