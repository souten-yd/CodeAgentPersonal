from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.level4_self_improvement_checkpoint import (
    RUNTIME_LEVEL as LEVEL4_RUNTIME_LEVEL,
    SCHEMA_VERSION as LEVEL4_CHECKPOINT_SCHEMA_VERSION,
    load_level4_self_improvement_checkpoint,
)

SCHEMA_VERSION = "atlas.automation_safety_profile.v1"
TRACK_PR = "PR-ATLAS-SCALE-147"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-148"
# Historical / default baseline. The runtime is no longer pinned to a single level;
# the effective level is resolved per selected profile (see RUNTIME_LEVEL_BY_PROFILE).
CURRENT_RUNTIME_LEVEL = "level_4_self_improvement_platform"
DEFAULT_RUNTIME_LEVEL = CURRENT_RUNTIME_LEVEL
MAX_RUNTIME_LEVEL = "level_8_fully_autonomous_code_agent"

PROFILE_REVIEW_ONLY = "review_only"
PROFILE_GUARDED_SINGLE_ACTION = "guarded_single_action"
PROFILE_SUPERVISED_BOUNDED_AUTO = "supervised_bounded_auto"
PROFILE_AUTONOMOUS_DEV_AGENT = "autonomous_dev_agent"

SELF_SCOPE_NONE = "none"
SELF_SCOPE_DOCS_TESTS_ONLY = "docs_tests_only"
SELF_SCOPE_ATLAS_NON_RUNTIME = "atlas_non_runtime"
SELF_SCOPE_ATLAS_RUNTIME_STRICT = "atlas_runtime_strict"
SELF_SCOPE_FULL_PLATFORM_STRICT = "full_platform_strict"

PROFILE_ORDER = {
    PROFILE_REVIEW_ONLY: 0,
    PROFILE_GUARDED_SINGLE_ACTION: 1,
    PROFILE_SUPERVISED_BOUNDED_AUTO: 2,
    PROFILE_AUTONOMOUS_DEV_AGENT: 3,
}

# Profile-dependent runtime model. The selected automation profile determines the
# effective runtime level. Defaults stay on the safe end; only autonomous_dev_agent
# reaches Level 8 (fully autonomous code agent), and even then full automation is
# bounded and only activated by an active pre-authorized envelope (never by profile
# selection alone). The forbidden capability flags below remain False at every level.
RUNTIME_LEVEL_BY_PROFILE = {
    PROFILE_REVIEW_ONLY: "level_0_review_only",
    PROFILE_GUARDED_SINGLE_ACTION: "level_1_guarded_single_step",
    PROFILE_SUPERVISED_BOUNDED_AUTO: "level_2_to_level4_supervised_bounded_auto",
    PROFILE_AUTONOMOUS_DEV_AGENT: "level_8_fully_autonomous_code_agent",
}
SELF_IMPROVEMENT_SCOPES = {
    SELF_SCOPE_NONE,
    SELF_SCOPE_DOCS_TESTS_ONLY,
    SELF_SCOPE_ATLAS_NON_RUNTIME,
    SELF_SCOPE_ATLAS_RUNTIME_STRICT,
    SELF_SCOPE_FULL_PLATFORM_STRICT,
}

_PROFILE_CAPABILITIES: dict[str, dict[str, Any]] = {
    PROFILE_REVIEW_ONLY: {
        "allows_file_mutation": False,
        "allows_command_execution": False,
        "allows_patch_apply": False,
        "allows_git_mutation": False,
        "allows_branch_creation": False,
        "allows_draft_pr_creation": False,
        "allows_draft_pr_update": False,
        "allows_auto_continue": False,
        "allows_autonomous_loop_execution": False,
        "requires_human_approval_for_mutation": True,
        "max_risk_level": "low",
    },
    PROFILE_GUARDED_SINGLE_ACTION: {
        "allows_file_mutation": True,
        "allows_command_execution": True,
        "allows_patch_apply": True,
        "allows_git_mutation": False,
        "allows_branch_creation": False,
        "allows_draft_pr_creation": False,
        "allows_draft_pr_update": False,
        "allows_auto_continue": False,
        "allows_autonomous_loop_execution": False,
        "requires_human_approval_for_mutation": True,
        "max_risk_level": "low",
    },
    PROFILE_SUPERVISED_BOUNDED_AUTO: {
        "allows_file_mutation": True,
        "allows_command_execution": True,
        "allows_patch_apply": True,
        "allows_git_mutation": True,
        "allows_branch_creation": True,
        "allows_draft_pr_creation": True,
        "allows_draft_pr_update": True,
        "allows_auto_continue": False,
        "allows_autonomous_loop_execution": False,
        "requires_human_approval_for_mutation": True,
        "max_risk_level": "medium",
    },
    PROFILE_AUTONOMOUS_DEV_AGENT: {
        "allows_file_mutation": True,
        "allows_command_execution": True,
        "allows_patch_apply": True,
        "allows_git_mutation": True,
        "allows_branch_creation": True,
        "allows_draft_pr_creation": True,
        "allows_draft_pr_update": True,
        "allows_auto_continue": True,
        "allows_autonomous_loop_execution": True,
        "requires_human_approval_for_mutation": False,
        "max_risk_level": "medium",
    },
}


def resolve_runtime_level_for_profile(profile: str) -> str:
    """Resolve the effective runtime level for a selected automation profile.

    Unknown profiles fall back to the safe historical baseline rather than escalating.
    """
    return RUNTIME_LEVEL_BY_PROFILE.get(profile, DEFAULT_RUNTIME_LEVEL)


def create_automation_safety_profile(
    *,
    profile: str = PROFILE_REVIEW_ONLY,
    data_root: str | Path | None = None,
    level4_checkpoint_path: str | Path | None = None,
    self_improvement_enabled: bool = False,
    self_improvement_scope: str = SELF_SCOPE_NONE,
    explicit_profile_selection: bool = False,
    strict_gate_approved: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    blocked: list[str] = []
    if profile not in PROFILE_ORDER:
        blocked.append("automation_safety_profile_not_allowed")
        profile = PROFILE_REVIEW_ONLY
    if self_improvement_scope not in SELF_IMPROVEMENT_SCOPES:
        blocked.append("self_improvement_scope_not_allowed")
        self_improvement_scope = SELF_SCOPE_NONE
    if not explicit_profile_selection:
        blocked.append("explicit_profile_selection_required")
    if self_improvement_enabled and self_improvement_scope == SELF_SCOPE_NONE:
        blocked.append("self_improvement_scope_required")
    if not self_improvement_enabled and self_improvement_scope != SELF_SCOPE_NONE:
        blocked.append("self_improvement_enabled_required_for_scope")
    if self_improvement_enabled and PROFILE_ORDER[profile] < PROFILE_ORDER[PROFILE_SUPERVISED_BOUNDED_AUTO]:
        blocked.append("self_improvement_requires_supervised_or_higher_profile")
    if self_improvement_enabled and not strict_gate_approved:
        blocked.append("strict_gate_approval_required_for_self_improvement")

    root = Path(data_root).expanduser().resolve() if data_root is not None else None
    checkpoint: dict[str, Any] | None = None
    checkpoint_path_value = ""
    if self_improvement_enabled:
        if level4_checkpoint_path is None or root is None:
            blocked.append("level4_checkpoint_required_for_self_improvement")
        else:
            checkpoint_path = Path(level4_checkpoint_path).expanduser().resolve()
            checkpoint_path_value = str(checkpoint_path)
            try:
                _ensure_under(root, checkpoint_path, "level4_checkpoint_outside_data_root")
                checkpoint = load_level4_self_improvement_checkpoint(manifest_path=checkpoint_path, data_root=root)
            except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
                blocked.append(str(exc))
    if checkpoint is not None:
        blocked.extend(_validate_level4_checkpoint(checkpoint))

    status = "active" if not blocked else "blocked"
    capabilities = dict(_PROFILE_CAPABILITIES[profile])
    result = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": _profile_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": sorted(set(blocked)),
        "runtime_level": resolve_runtime_level_for_profile(profile),
        "runtime_level_model": "profile_dependent",
        "runtime_level_by_profile": dict(RUNTIME_LEVEL_BY_PROFILE),
        "default_runtime_level": DEFAULT_RUNTIME_LEVEL,
        "max_runtime_level": MAX_RUNTIME_LEVEL,
        "automation_safety_profile": profile,
        "profile_rank": PROFILE_ORDER[profile],
        "explicit_profile_selection_required": True,
        "explicit_profile_selection": bool(explicit_profile_selection),
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_improvement_enabled": bool(self_improvement_enabled and not blocked),
        "requested_self_improvement_enabled": bool(self_improvement_enabled),
        "self_improvement_scope": self_improvement_scope,
        "strict_gate_required_for_self_improvement": True,
        "strict_gate_approved": bool(strict_gate_approved),
        "level4_checkpoint_required_for_self_improvement": True,
        "level4_checkpoint_path": checkpoint_path_value,
        "automation_safety_profile_framework_enabled": status == "active",
        "capabilities": capabilities,
        "review_only": profile == PROFILE_REVIEW_ONLY,
        "guarded_single_action": profile == PROFILE_GUARDED_SINGLE_ACTION,
        "supervised_bounded_auto": profile == PROFILE_SUPERVISED_BOUNDED_AUTO,
        "autonomous_dev_agent": profile == PROFILE_AUTONOMOUS_DEV_AGENT,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
        "direct_merge_performed": False,
        "remote_git_push_performed": False,
        "stable_runtime_mutation_performed": False,
    }
    return validate_automation_safety_profile(result)


def validate_automation_safety_profile(profile: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "runtime_level",
        "automation_safety_profile",
        "profile_rank",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "self_improvement_enabled",
        "requested_self_improvement_enabled",
        "self_improvement_scope",
        "strict_gate_required_for_self_improvement",
        "level4_checkpoint_required_for_self_improvement",
        "automation_safety_profile_framework_enabled",
        "capabilities",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "self_apply_enabled",
        "self_modification_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
        "direct_merge_performed",
        "remote_git_push_performed",
        "stable_runtime_mutation_performed",
    ]
    missing = [field for field in required if field not in profile]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    name = str(profile.get("automation_safety_profile"))
    capabilities = profile.get("capabilities")
    false_required = [
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "self_apply_enabled",
        "self_modification_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
        "direct_merge_performed",
        "remote_git_push_performed",
        "stable_runtime_mutation_performed",
    ]
    invariants = {
        "schema_version": profile.get("schema_version") == SCHEMA_VERSION,
        "track_pr": profile.get("track_pr") == TRACK_PR,
        "next_required_pr": profile.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": profile.get("status") in {"active", "blocked"},
        "runtime_level": profile.get("runtime_level") == resolve_runtime_level_for_profile(name),
        "automation_safety_profile": name in PROFILE_ORDER,
        "profile_rank": profile.get("profile_rank") == PROFILE_ORDER.get(name),
        "explicit_profile_selection_required": profile.get("explicit_profile_selection_required") is True,
        "backend_authoritative": profile.get("backend_authoritative") is True,
        "strict_gate_required_for_self_improvement": profile.get("strict_gate_required_for_self_improvement") is True,
        "level4_checkpoint_required_for_self_improvement": profile.get("level4_checkpoint_required_for_self_improvement") is True,
        "automation_safety_profile_framework_enabled": profile.get("automation_safety_profile_framework_enabled") is (profile.get("status") == "active"),
        "capabilities": isinstance(capabilities, dict) and capabilities == _PROFILE_CAPABILITIES.get(name),
        "self_improvement_scope": profile.get("self_improvement_scope") in SELF_IMPROVEMENT_SCOPES,
        "blocked_reasons": profile.get("status") != "blocked" or bool(profile.get("blocking_reasons")),
    }
    invariants.update({key: profile.get(key) is False for key in false_required})
    if profile.get("self_improvement_enabled") is True:
        invariants["self_improvement_scope_active"] = profile.get("self_improvement_scope") != SELF_SCOPE_NONE
        invariants["self_improvement_profile_rank"] = int(profile.get("profile_rank") or -1) >= PROFILE_ORDER[PROFILE_SUPERVISED_BOUNDED_AUTO]
        invariants["strict_gate_approved"] = profile.get("strict_gate_approved") is True
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return profile


def write_automation_safety_profile(*, data_root: str | Path, profile: dict[str, Any]) -> Path:
    validated = validate_automation_safety_profile(profile)
    root = Path(data_root).expanduser().resolve()
    profile_id = str(validated["profile_id"])
    path = root / "atlas" / "automation_safety_profiles" / profile_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_automation_safety_profile(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_automation_safety_profile(json.loads(path.read_text(encoding="utf-8")))


def _validate_level4_checkpoint(checkpoint: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if checkpoint.get("schema_version") != LEVEL4_CHECKPOINT_SCHEMA_VERSION:
        blocked.append("unsupported_level4_checkpoint_schema")
    if checkpoint.get("transition_authorized") is not True:
        blocked.append("level4_checkpoint_authorization_required")
    if checkpoint.get("runtime_level") != LEVEL4_RUNTIME_LEVEL:
        blocked.append("level4_runtime_level_required")
    if checkpoint.get("level4_self_improvement_checkpoint_enabled") is not True:
        blocked.append("level4_checkpoint_enabled_required")
    for key in (
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "self_apply_enabled",
        "self_modification_enabled",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
        "direct_merge_performed",
        "remote_git_push_performed",
        "stable_runtime_mutation_performed",
    ):
        if checkpoint.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _profile_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"automation_safety_profile_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
