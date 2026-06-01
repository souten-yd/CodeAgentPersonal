from __future__ import annotations

from typing import Any

PROFILES = {
    "review_only",
    "guarded_single_action",
    "supervised_bounded_auto",
    "autonomous_dev_agent",
}
PRESETS = {
    "review_only",
    "single_action",
    "supervised_auto",
    "autonomous_custom",
    "autonomous_bounded_dev",
    "full_auto",
    "full_auto_multi_item_v1",
}
AUTOMATION_LEVELS = {
    "manual_only",
    "guarded_low_risk",
    "supervised_auto",
    "full_autopilot",
}
ENVELOPES = {
    "none",
    "pre_authorized_bounded_dev_envelope",
    "pre_authorized_self_improvement_envelope",
}

RUNTIME_LEVEL_BY_PROFILE = {
    "review_only": "level_0_review_only",
    "guarded_single_action": "level_1_guarded_single_step",
    "supervised_bounded_auto": "level_2_to_level4_supervised_bounded_auto",
    "autonomous_dev_agent": "level_8_fully_autonomous_code_agent",
}

_PROFILE_BY_PRESET = {
    "review_only": "review_only",
    "single_action": "guarded_single_action",
    "supervised_auto": "supervised_bounded_auto",
    "autonomous_custom": "autonomous_dev_agent",
    "autonomous_bounded_dev": "autonomous_dev_agent",
    "full_auto": "autonomous_dev_agent",
    "full_auto_multi_item_v1": "autonomous_dev_agent",
}

_AUTOMATION_LEVEL_BY_PRESET = {
    "review_only": "manual_only",
    "single_action": "guarded_low_risk",
    "supervised_auto": "supervised_auto",
    "autonomous_custom": "full_autopilot",
    "autonomous_bounded_dev": "full_autopilot",
    "full_auto": "full_autopilot",
    "full_auto_multi_item_v1": "full_autopilot",
}

_ENVELOPE_BY_PRESET = {
    "autonomous_bounded_dev": "pre_authorized_bounded_dev_envelope",
}

_DEFAULT_BOUNDS = {
    "max_actions": 0,
    "max_retries": 0,
    "max_changed_files": 0,
    "max_runtime_seconds": 0,
    "allowed_paths": [],
    "blocked_paths": [],
}

_BOUNDED_DEV_BOUNDS = {
    "max_actions": 12,
    "max_retries": 2,
    "max_changed_files": 25,
    "max_runtime_seconds": 1800,
    "allowed_paths": ["app/", "web/", "tests/", "docs/"],
    "blocked_paths": [".git/", ".github/workflows/", "scripts/release/", "secrets/", "infra/"],
}

_SELF_IMPROVEMENT_BOUNDS = {
    "max_actions": 6,
    "max_retries": 1,
    "max_changed_files": 12,
    "max_runtime_seconds": 1200,
    "allowed_paths": ["app/atlas/", "docs/", "tests/"],
    "blocked_paths": [".git/", ".github/workflows/", "scripts/release/", "infra/", "app/server.py", "main.py"],
}


def normalize_automation_profile(
    *,
    profile: str = "",
    preset_id: str = "",
    automation_level: str = "",
    envelope_id: str = "",
    envelope_active: bool = False,
    self_improvement: bool = False,
    strict_gate_approved: bool = False,
    bounds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested_profile = _norm(profile)
    requested_preset = _norm(preset_id)
    requested_level = _norm(automation_level)
    requested_envelope = _norm(envelope_id)
    blocking_reasons: list[str] = []

    preset = requested_preset if requested_preset in PRESETS else ""
    if requested_preset and not preset:
        blocking_reasons.append("unknown_preset_fell_back_to_review_only")

    resolved_profile = requested_profile if requested_profile in PROFILES else ""
    if not resolved_profile and preset:
        resolved_profile = _PROFILE_BY_PRESET[preset]
    if not resolved_profile:
        if requested_profile:
            blocking_reasons.append("unknown_profile_fell_back_to_review_only")
        resolved_profile = "review_only"

    resolved_level = requested_level if requested_level in AUTOMATION_LEVELS else ""
    if not resolved_level and preset:
        resolved_level = _AUTOMATION_LEVEL_BY_PRESET[preset]
    if not resolved_level:
        if requested_level:
            blocking_reasons.append("unknown_automation_level_fell_back_to_manual_only")
        resolved_level = "manual_only"

    resolved_envelope = requested_envelope if requested_envelope in ENVELOPES else ""
    if not resolved_envelope and preset:
        resolved_envelope = _ENVELOPE_BY_PRESET.get(preset, "none")
    if not resolved_envelope:
        if requested_envelope:
            blocking_reasons.append("unknown_envelope_fell_back_to_none")
        resolved_envelope = "none"

    if resolved_envelope == "pre_authorized_self_improvement_envelope":
        self_improvement = True
        if not strict_gate_approved:
            blocking_reasons.append("strict_gate_required_by_self_improvement_envelope")

    envelope_can_activate = (
        bool(envelope_active)
        and resolved_profile == "autonomous_dev_agent"
        and resolved_envelope == "pre_authorized_bounded_dev_envelope"
    )
    self_envelope_can_activate = (
        bool(envelope_active)
        and resolved_profile == "autonomous_dev_agent"
        and resolved_envelope == "pre_authorized_self_improvement_envelope"
        and bool(strict_gate_approved)
    )
    autonomous_loop_active = envelope_can_activate or self_envelope_can_activate
    full_auto_capable = resolved_profile == "autonomous_dev_agent" or resolved_level == "full_autopilot"

    resolved_bounds = _resolve_bounds(resolved_envelope, bounds)
    return {
        "profile": resolved_profile,
        "preset_id": preset or "review_only",
        "automation_level": resolved_level,
        "envelope_id": resolved_envelope,
        "envelope_active": bool(envelope_active and resolved_envelope != "none"),
        "self_improvement": bool(self_improvement),
        "runtime_level": RUNTIME_LEVEL_BY_PROFILE[resolved_profile],
        "full_auto_capable": bool(full_auto_capable),
        "autonomous_loop_active": bool(autonomous_loop_active and not blocking_reasons),
        "critical_handling_default": _critical_default(resolved_profile, preset or "", resolved_envelope, bool(self_improvement)),
        "critical_user_approval_required": True,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "self_apply_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "vue_authority_enabled": False,
        "arbitrary_command_execution_enabled": False,
        "max_actions": resolved_bounds["max_actions"],
        "max_retries": resolved_bounds["max_retries"],
        "max_changed_files": resolved_bounds["max_changed_files"],
        "max_runtime_seconds": resolved_bounds["max_runtime_seconds"],
        "allowed_paths": list(resolved_bounds["allowed_paths"]),
        "blocked_paths": list(resolved_bounds["blocked_paths"]),
        "blocking_reasons": sorted(set(blocking_reasons)),
    }


def is_full_auto_context(*, preset_id: str = "", automation_level: str = "", profile: str = "", envelope_id: str = "", envelope_active: bool = False) -> bool:
    resolved = normalize_automation_profile(
        profile=profile,
        preset_id=preset_id,
        automation_level=automation_level,
        envelope_id=envelope_id,
        envelope_active=envelope_active,
    )
    return bool(resolved["full_auto_capable"])


def _resolve_bounds(envelope_id: str, override: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(_DEFAULT_BOUNDS)
    if envelope_id == "pre_authorized_bounded_dev_envelope":
        base.update(_BOUNDED_DEV_BOUNDS)
    elif envelope_id == "pre_authorized_self_improvement_envelope":
        base.update(_SELF_IMPROVEMENT_BOUNDS)
    if isinstance(override, dict):
        for key in base:
            if key in override:
                base[key] = list(override[key]) if isinstance(base[key], list) else override[key]
    return base


def _critical_default(profile: str, preset: str, envelope_id: str, self_improvement: bool) -> str:
    if self_improvement or envelope_id == "pre_authorized_self_improvement_envelope":
        return "ask"
    if preset in {"autonomous_custom", "autonomous_bounded_dev", "full_auto", "full_auto_multi_item_v1"}:
        return "auto"
    if profile == "review_only":
        return "block"
    return "ask"


def _norm(value: object) -> str:
    return str(value or "").strip().lower()
