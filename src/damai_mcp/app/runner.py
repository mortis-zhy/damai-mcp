"""Execute an :class:`AppProfile`'s steps against a real Android device.

The runner is intentionally tiny: each :class:`Step` action is a string
mapped to a small async function. Anything beyond the built-in actions is
out of scope (use a custom profile plugin).

The runner returns a structured :class:`RunResult` with per-step outcome
so callers (MCP/CLI/agent) can debug what went wrong without crawling logs.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

# Atomic ops used by the actions
from ..actions.actions import (
    input_text as _input_text,
)
from ..actions.actions import (
    tap as _tap,
)
from ..inspector.find import (
    find_by_text as _find_by_text,
)
from ..inspector.find import (
    wait_for_element as _wait_for_element,
)
from ..utils.logging import logger
from .profile import AppProfile, RunContext, Step


@dataclass
class StepResult:
    step_name: str
    action: str
    started_at_ms: int
    finished_at_ms: int | None = None
    status: str = "pending"  # "ok" | "failed" | "skipped"
    output: dict[str, Any] | None = None
    error: str | None = None

    @property
    def elapsed_ms(self) -> int:
        if self.finished_at_ms is None:
            return 0
        return self.finished_at_ms - self.started_at_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step_name,
            "action": self.action,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class RunResult:
    profile: str
    package: str
    item_id: str
    status: str  # "submitted" | "needs_human" | "failed"
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "package": self.package,
            "item_id": self.item_id,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "error": self.error,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---- action implementations ----------------------------------------------

async def _action_open_detail(
    step: Step, ctx: RunContext, profile: AppProfile,
) -> dict[str, Any]:
    """Open the show's detail page.

    Currently launches via the package launcher (most reliable cross-app).
    URL deep-links can be added later; for now we reuse the existing
    ``damai_open_concert`` shape via profile hooks.
    """
    # Reuse launcher logic if present in profile options, else fall back
    # to a generic intent: monkey calls the launcher via `am start`.
    from ..device.adb import run_adb
    pkg = profile.package_name
    cmd = ["shell", "am", "start", "-n", f"{pkg}/.homepage.MainActivity"]
    try:
        await run_adb(ctx.device_id, cmd, timeout=10.0)
        return {"opened_pkg": pkg}
    except Exception:
        fallback = [
            "shell", "monkey", "-p", pkg,
            "-c", "android.intent.category.LAUNCHER", "1",
        ]
        await run_adb(ctx.device_id, fallback, timeout=10.0)
        return {"opened_pkg": pkg, "via": "monkey"}


async def _action_wait_text(step: Step, ctx: RunContext, *_a: Any) -> dict[str, Any]:
    text = step.args["text"]
    el = await _wait_for_element(
        ctx.device_id, f"text={text}", timeout=step.timeout_sec,
    )
    return {"found": text, "center": list(el.center), "text": el.text}


async def _action_tap_text(step: Step, ctx: RunContext, *_a: Any) -> dict[str, Any]:
    text = step.args["text"]
    exact = step.args.get("exact", False)
    el = await _find_by_text(
        ctx.device_id, text, exact=exact, timeout=step.timeout_sec,
    )
    await _tap(ctx.device_id, *el.center)
    return {"tapped_text": text, "center": list(el.center)}


async def _action_tap_index(step: Step, ctx: RunContext, *_a: Any) -> dict[str, Any]:
    text = step.args["text"]
    index = int(step.args.get("index", 0))
    # Find all matches
    from ..device.adb import run_adb
    out = await run_adb(
        ctx.device_id,
        ["shell", "uiautomator", "dump", "/sdcard/ui.xml"],
        timeout=10.0,
    )
    if out.returncode != 0:
        raise RuntimeError(f"uiautomator dump failed: {out.stderr}")
    # Parse via the existing dump
    from ..inspector.dump import dump_ui
    elements = await dump_ui(ctx.device_id, refresh=True)
    matches = [e for e in elements if text in (e.text or "")]
    if index >= len(matches):
        raise RuntimeError(f"only {len(matches)} matches for {text!r}, wanted index {index}")
    el = matches[index]
    await _tap(ctx.device_id, *el.center)
    return {"tapped_index": index, "text": el.text}


async def _action_select_checkbox(step: Step, ctx: RunContext, *_a: Any) -> dict[str, Any]:
    label = step.args["label"]
    el = await _find_by_text(
        ctx.device_id, label, exact=False, timeout=step.timeout_sec,
    )
    # Walk left to find a checkbox, otherwise tap the label
    # Cheap fallback: just tap the label text — works on 大麦/猫眼
    await _tap(ctx.device_id, *el.center)
    return {"toggled_label": label}


async def _action_check_text(step: Step, ctx: RunContext, *_a: Any) -> dict[str, Any]:
    text = step.args["text"]
    el = await _find_by_text(
        ctx.device_id, text, exact=step.args.get("exact", True),
        timeout=step.timeout_sec,
    )
    return {"present": True, "text": el.text}


async def _action_sleep(step: Step, *_a: Any) -> dict[str, Any]:
    sec = float(step.args.get("seconds", 1.0))
    await asyncio.sleep(sec)
    return {"slept_sec": sec}


async def _action_input_text(step: Step, ctx: RunContext, *_a: Any) -> dict[str, Any]:
    text = step.args["text"]
    await _input_text(ctx.device_id, text, delay_ms=step.args.get("delay_ms", 0))
    return {"input_len": len(text)}


_ACTION_TABLE = {
    "open_detail": _action_open_detail,
    "wait_text": _action_wait_text,
    "tap_text": _action_tap_text,
    "tap_index": _action_tap_index,
    "select_checkbox": _action_select_checkbox,
    "check_text": _action_check_text,
    "sleep": _action_sleep,
    "input_text": _action_input_text,
}


async def run_profile(
    profile: AppProfile,
    device_id: str,
    item_id: str,
    options: dict[str, Any] | None = None,
) -> RunResult:
    """Execute the profile against the device."""
    ctx = RunContext(device_id=device_id, item_id=item_id, options=options or {})
    out = RunResult(
        profile=profile.name,
        package=profile.package_name,
        item_id=item_id,
        status="needs_human",
    )

    logger.info(f"[runner] start profile={profile.name} device={device_id} item={item_id}")
    for step in profile.steps:
        sr = StepResult(
            step_name=step.name, action=step.action, started_at_ms=_now_ms(),
        )
        try:
            handler = _ACTION_TABLE.get(step.action)
            if handler is None:
                raise NotImplementedError(f"unknown action {step.action!r}")
            out_step = await handler(step, ctx, profile)
            sr.output = out_step
            sr.status = "ok"
        except Exception as exc:
            sr.status = "failed"
            sr.error = str(exc)
            out.error = f"{step.name}: {exc}"
            out.steps.append(sr)
            if not step.continue_on_fail:
                out.status = "failed"
                sr.finished_at_ms = _now_ms()
                logger.error(f"[runner] step {step.name!r} failed: {exc}")
                break
            sr.finished_at_ms = _now_ms()
            out.steps.append(sr)
            logger.warning(f"[runner] step {step.name!r} failed: {exc} (continuing)")
            continue
        sr.finished_at_ms = _now_ms()
        out.steps.append(sr)
        logger.info(f"[runner] step {step.name!r} ok in {sr.elapsed_ms}ms")
        ctx.last_result = sr.output

    if out.status != "failed":
        out.status = "submitted"

    logger.info(f"[runner] finish status={out.status}")
    return out
