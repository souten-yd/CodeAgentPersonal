"""Pre-authorized bounded execution envelopes for Atlas Automation Profiles.

Envelopes are bound recipes (max_files, max_loops, command_allowlist, etc.)
that pair with the existing capability tiers defined in
``app.atlas.automation_safety_profile``. They do not introduce new capability
tiers; they describe a recipe for safely activating the autonomous_dev_agent
capabilities inside a pre-authorised scope.

The envelope itself does not perform execution. ``autonomous_loop_envelope_runner``
reads a confirmed envelope manifest and starts the autonomous loop within its
bounds. The envelope record is the artefact that records the user's explicit
permission to lift the default Level-4 lockouts inside a bounded scope.

This module is I/O free; it returns plain dicts that callers can validate,
write to disk, or include in HTTP responses.
"""

from __future__ import annotations

from typing import Any

from app.atlas.automation_safety_profile import (
    PROFILE_AUTONOMOUS_DEV_AGENT,
    SELF_SCOPE_ATLAS_RUNTIME_STRICT,
    SELF_SCOPE_NONE,
)

SCHEMA_VERSION = "atlas.pre_authorized_envelope.v1"
TRACK_PR = "POST-SCALE-160-CLAUDE-CHAT-COMPLETE-AUTOMATION-PROFILE"

ENVELOPE_NONE = "none"
ENVELOPE_BOUNDED_DEV = "pre_authorized_bounded_dev_envelope"
ENVELOPE_SELF_IMPROVEMENT = "pre_authorized_self_improvement_envelope"

ALLOWED_ENVELOPES = frozenset(
    {ENVELOPE_NONE, ENVELOPE_BOUNDED_DEV, ENVELOPE_SELF_IMPROVEMENT}
)

_ENVELOPE_RECIPES: dict[str, dict[str, Any]] = {
    ENVELOPE_NONE: {
        "envelope_id": ENVELOPE_NONE,
        "label": "No envelope (per-action approval)",
        "automation_safety_profile": None,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_required": False,
        "level4_checkpoint_required": False,
        "candidate_workspace_required": False,
        "draft_pr_only": True,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_self_improvement_enabled": False,
        "bounds": {
            "max_actions_per_loop": 0,
            "max_retries_per_action": 0,
            "max_runtime_seconds": 0,
            "max_files_changed": 0,
            "max_risk_level": "low",
            "allowed_paths": [],
            "blocked_paths": [],
            "command_allowlist": [],
        },
    },
    ENVELOPE_BOUNDED_DEV: {
        "envelope_id": ENVELOPE_BOUNDED_DEV,
        "label": "Autonomous Bounded Dev",
        "automation_safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_required": False,
        "level4_checkpoint_required": False,
        "candidate_workspace_required": True,
        "draft_pr_only": True,
        "autonomous_execution_enabled": True,
        "autonomous_loop_execution_enabled": True,
        "automatic_patch_apply_enabled": True,
        "automatic_self_improvement_enabled": False,
        "bounds": {
            "max_actions_per_loop": 12,
            "max_retries_per_action": 2,
            "max_runtime_seconds": 1800,
            "max_files_changed": 25,
            "max_risk_level": "medium",
            "allowed_paths": ["app/", "web/", "tests/", "docs/"],
            "blocked_paths": [
                ".git/",
                ".github/workflows/",
                "scripts/release/",
                "secrets/",
                "infra/",
            ],
            "command_allowlist": [
                "python -m pytest",
                "pytest",
                "ruff",
                "ruff check",
                "mypy",
                "node --version",
                "git status",
                "git diff",
            ],
        },
    },
    ENVELOPE_SELF_IMPROVEMENT: {
        "envelope_id": ENVELOPE_SELF_IMPROVEMENT,
        "label": "Autonomous Self-Improvement",
        "automation_safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "self_improvement_enabled": True,
        "self_improvement_scope": SELF_SCOPE_ATLAS_RUNTIME_STRICT,
        "strict_gate_required": True,
        "level4_checkpoint_required": True,
        "candidate_workspace_required": True,
        "draft_pr_only": True,
        "autonomous_execution_enabled": True,
        "autonomous_loop_execution_enabled": True,
        "automatic_patch_apply_enabled": True,
        "automatic_self_improvement_enabled": True,
        "bounds": {
            "max_actions_per_loop": 6,
            "max_retries_per_action": 1,
            "max_runtime_seconds": 1200,
            "max_files_changed": 12,
            "max_risk_level": "medium",
            "allowed_paths": ["app/atlas/", "docs/", "tests/"],
            "blocked_paths": [
                ".git/",
                ".github/workflows/",
                "scripts/release/",
                "infra/",
                "app/server.py",
                "main.py",
            ],
            "command_allowlist": [
                "python -m pytest",
                "pytest",
                "ruff check",
                "git status",
                "git diff",
            ],
        },
    },
}


def list_envelopes() -> list[dict[str, Any]]:
    """Return all envelope recipes as plain dicts (deep-copied)."""

    return [_deep_copy(_ENVELOPE_RECIPES[name]) for name in ALLOWED_ENVELOPES]


def get_envelope(envelope_id: str) -> dict[str, Any]:
    """Return the recipe for ``envelope_id``.

    Unknown ids return a blocked recipe so callers do not need to branch on
    membership checks before requesting capabilities.
    """

    if envelope_id not in ALLOWED_ENVELOPES:
        return {
            "schema_version": SCHEMA_VERSION,
            "track_pr": TRACK_PR,
            "envelope_id": str(envelope_id),
            "status": "blocked",
            "blocking_reasons": ["envelope_unknown"],
            "automation_safety_profile": None,
            "self_improvement_enabled": False,
            "self_improvement_scope": SELF_SCOPE_NONE,
            "autonomous_execution_enabled": False,
            "autonomous_loop_execution_enabled": False,
            "automatic_patch_apply_enabled": False,
            "automatic_self_improvement_enabled": False,
            "bounds": {},
        }
    recipe = _deep_copy(_ENVELOPE_RECIPES[envelope_id])
    recipe["schema_version"] = SCHEMA_VERSION
    recipe["track_pr"] = TRACK_PR
    recipe["status"] = "active" if envelope_id != ENVELOPE_NONE else "inactive"
    recipe["blocking_reasons"] = []
    return recipe


def build_envelope_manifest(
    *,
    envelope_id: str,
    safety_profile: dict[str, Any],
    confirmation_text: str,
    created_at: str,
) -> dict[str, Any]:
    """Combine a safety profile with an envelope recipe to produce a manifest.

    The manifest records the user's explicit pre-authorization to activate the
    derived runtime flags (``autonomous_execution_enabled`` etc.) inside the
    bounded scope. It does NOT mutate the safety profile manifest; callers must
    persist this envelope manifest separately so the safety profile invariants
    (which keep all those flags ``False``) remain intact.
    """

    recipe = get_envelope(envelope_id)
    blocked: list[str] = list(recipe.get("blocking_reasons") or [])

    if not isinstance(safety_profile, dict):
        blocked.append("safety_profile_missing")
        safety_profile = {}

    if safety_profile.get("status") != "active":
        blocked.append("safety_profile_not_active")

    expected_text_modern = "SELECT AUTOMATION PROFILE"
    expected_text_legacy = "SELECT AUTOMATION SAFETY PROFILE"
    if confirmation_text not in (expected_text_modern, expected_text_legacy):
        blocked.append("confirmation_text_required")

    expected_profile = recipe.get("automation_safety_profile")
    if (
        envelope_id != ENVELOPE_NONE
        and expected_profile is not None
        and safety_profile.get("automation_safety_profile") != expected_profile
    ):
        blocked.append("safety_profile_mismatch")

    if recipe.get("self_improvement_enabled") and not safety_profile.get(
        "self_improvement_enabled"
    ):
        blocked.append("self_improvement_required_by_envelope")

    if recipe.get("strict_gate_required") and not safety_profile.get(
        "strict_gate_approved"
    ):
        blocked.append("strict_gate_required_by_envelope")

    if recipe.get("level4_checkpoint_required") and not safety_profile.get(
        "level4_checkpoint_path"
    ):
        blocked.append("level4_checkpoint_required_by_envelope")

    status = "active" if not blocked and envelope_id != ENVELOPE_NONE else (
        "blocked" if blocked else "inactive"
    )

    activation_active = status == "active"
    return {
        "schema_version": SCHEMA_VERSION,
        "track_pr": TRACK_PR,
        "envelope_id": envelope_id,
        "label": recipe.get("label"),
        "created_at": created_at,
        "status": status,
        "blocking_reasons": sorted(set(blocked)),
        "confirmation_text_accepted": confirmation_text
        in (expected_text_modern, expected_text_legacy),
        "automation_safety_profile": safety_profile.get(
            "automation_safety_profile"
        ),
        "safety_profile_id": safety_profile.get("profile_id"),
        "self_improvement_enabled": bool(
            safety_profile.get("self_improvement_enabled")
        )
        and activation_active,
        "self_improvement_scope": safety_profile.get("self_improvement_scope")
        or SELF_SCOPE_NONE,
        "candidate_workspace_required": bool(
            recipe.get("candidate_workspace_required")
        ),
        "draft_pr_only": bool(recipe.get("draft_pr_only")),
        "autonomous_execution_enabled": bool(
            recipe.get("autonomous_execution_enabled")
        )
        and activation_active,
        "autonomous_loop_execution_enabled": bool(
            recipe.get("autonomous_loop_execution_enabled")
        )
        and activation_active,
        "automatic_patch_apply_enabled": bool(
            recipe.get("automatic_patch_apply_enabled")
        )
        and activation_active,
        "automatic_self_improvement_enabled": bool(
            recipe.get("automatic_self_improvement_enabled")
        )
        and activation_active,
        "bounds": _deep_copy(recipe.get("bounds") or {}),
        "backend_authoritative": True,
    }


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
