from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.conversational_shell_contract.v1"
TRACK_PR = "PR-ATLAS-SCALE-151"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-152"
CURRENT_RUNTIME_LEVEL = "level_4_self_improvement_platform"

WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR = "software_development_repair"
WORK_TARGET_PLATFORM_SELF_IMPROVEMENT = "platform_self_improvement"
WORK_TARGET_MODES = {
    WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
}

STATE_IDLE = "idle"
STATE_UNDERSTANDING_GOAL = "understanding_goal"
STATE_PLANNING = "planning"
STATE_NEEDS_SCOPE_CONFIRMATION = "needs_scope_confirmation"
STATE_PREVIEWING_CHANGES = "previewing_changes"
STATE_AWAITING_APPROVAL = "awaiting_approval"
STATE_RUNNING_DRY_RUN = "running_dry_run"
STATE_APPLYING_CANDIDATE = "applying_candidate"
STATE_VERIFYING_CANDIDATE = "verifying_candidate"
STATE_PROMOTING_CANDIDATE = "promoting_candidate"
STATE_DRAFT_PR_READY = "draft_pr_ready"
STATE_BLOCKED = "blocked"
STATE_RECOVERABLE_FAILURE = "recoverable_failure"
STATE_RECOVERED = "recovered"
CONVERSATIONAL_STATES = {
    STATE_IDLE,
    STATE_UNDERSTANDING_GOAL,
    STATE_PLANNING,
    STATE_NEEDS_SCOPE_CONFIRMATION,
    STATE_PREVIEWING_CHANGES,
    STATE_AWAITING_APPROVAL,
    STATE_RUNNING_DRY_RUN,
    STATE_APPLYING_CANDIDATE,
    STATE_VERIFYING_CANDIDATE,
    STATE_PROMOTING_CANDIDATE,
    STATE_DRAFT_PR_READY,
    STATE_BLOCKED,
    STATE_RECOVERABLE_FAILURE,
    STATE_RECOVERED,
}

REQUIRED_VISIBLE_REGIONS = {
    "conversation_transcript",
    "goal_input",
    "current_phase_card",
    "next_action_card",
    "safety_profile_badge",
    "work_target_mode_selector",
    "changed_files_summary",
    "verification_summary",
    "recovery_status",
    "primary_cta",
}

_REQUIRED_FALSE_FLAGS = (
    "requires_npm_build",
    "requires_vite",
    "requires_vue_runtime",
    "command_execution_enabled",
    "command_execution_performed",
    "execution_authority_enabled",
    "autonomous_execution_enabled",
    "auto_continue_enabled",
    "execute_all_enabled",
    "patch_apply_enabled",
    "candidate_apply_enabled",
    "candidate_promotion_enabled",
    "stable_runtime_mutation_enabled",
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "self_apply_enabled",
    "self_modification_enabled",
    "vue_authoritative",
    "vue_approval_authority_enabled",
    "vue_execution_controls_enabled",
    "default_ui_promotion_enabled",
    "work_target_mode_authorizes_self_improvement",
)


def create_conversational_shell_contract(
    *,
    goal: str,
    work_target_mode: str = WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    conversation_state: str = STATE_IDLE,
    selected_safety_profile: str = "review_only",
    current_phase: str = "conversational_atlas_ux",
    next_action: str = "prepare_shell_implementation",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    blocked: list[str] = []
    normalized_goal = str(goal).strip()
    normalized_mode = str(work_target_mode).strip()
    normalized_state = str(conversation_state).strip()
    normalized_profile = str(selected_safety_profile).strip()

    if not normalized_goal:
        blocked.append("goal_required")
    if normalized_mode not in WORK_TARGET_MODES:
        blocked.append("work_target_mode_not_allowed")
    if normalized_state not in CONVERSATIONAL_STATES:
        blocked.append("conversation_state_not_allowed")
    if not normalized_profile:
        blocked.append("selected_safety_profile_required")

    status = "ready" if not blocked else "blocked"
    contract = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": _contract_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": sorted(set(blocked)),
        "runtime_level": CURRENT_RUNTIME_LEVEL,
        "current_phase": str(current_phase),
        "next_action": str(next_action),
        "goal": normalized_goal,
        "conversation_state": normalized_state,
        "selected_safety_profile": normalized_profile,
        "work_target_mode": normalized_mode,
        "allowed_work_target_modes": sorted(WORK_TARGET_MODES),
        "allowed_conversation_states": sorted(CONVERSATIONAL_STATES),
        "required_visible_regions": sorted(REQUIRED_VISIBLE_REGIONS),
        "primary_cta_count": 1,
        "workflow_state_source": "backend_workflow_state",
        "backend_authoritative": True,
        "buildless_shell_contract_enabled": status == "ready",
        "atlas_next_preview_optional": True,
        "default_root_ui": "ui.html",
        "default_route_promotion_allowed": False,
        "self_improvement_requires_backend_gates": True,
        "platform_self_improvement_mode_available": True,
        "ordinary_software_work_mode_available": True,
        "shell_contract_artifact_only": True,
        "requires_npm_build": False,
        "requires_vite": False,
        "requires_vue_runtime": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "execution_authority_enabled": False,
        "autonomous_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "patch_apply_enabled": False,
        "candidate_apply_enabled": False,
        "candidate_promotion_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "vue_authoritative": False,
        "vue_approval_authority_enabled": False,
        "vue_execution_controls_enabled": False,
        "default_ui_promotion_enabled": False,
        "work_target_mode_authorizes_self_improvement": False,
        "allowed_next_actions": [
            "review_conversational_shell_contract",
            "implement_buildless_shell_display",
            "bind_backend_owned_work_target_mode_selector",
        ],
        "forbidden_actions": [
            "enable_vue_authority",
            "promote_atlas_next_default_route",
            "require_vite_build_for_default_shell",
            "execute_commands",
            "apply_candidate_patch",
            "promote_candidate",
            "mutate_stable_runtime",
            "self_apply",
            "direct_merge",
        ],
    }
    return validate_conversational_shell_contract(contract)


def validate_conversational_shell_contract(contract: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "runtime_level",
        "goal",
        "conversation_state",
        "selected_safety_profile",
        "work_target_mode",
        "allowed_work_target_modes",
        "allowed_conversation_states",
        "required_visible_regions",
        "primary_cta_count",
        "workflow_state_source",
        "backend_authoritative",
        "buildless_shell_contract_enabled",
        "atlas_next_preview_optional",
        "default_root_ui",
        "default_route_promotion_allowed",
        "self_improvement_requires_backend_gates",
        "shell_contract_artifact_only",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in contract]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    is_blocked = contract.get("status") == "blocked"
    invariants = {
        "schema_version": contract.get("schema_version") == SCHEMA_VERSION,
        "track_pr": contract.get("track_pr") == TRACK_PR,
        "next_required_pr": contract.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": contract.get("status") in {"ready", "blocked"},
        "blocked_reasons": not is_blocked or bool(contract.get("blocking_reasons")),
        "runtime_level": contract.get("runtime_level") == CURRENT_RUNTIME_LEVEL,
        "goal": is_blocked or bool(str(contract.get("goal", "")).strip()),
        "conversation_state": contract.get("conversation_state") in CONVERSATIONAL_STATES,
        "work_target_mode": contract.get("work_target_mode") in WORK_TARGET_MODES,
        "allowed_work_target_modes": set(contract.get("allowed_work_target_modes", [])) == WORK_TARGET_MODES,
        "allowed_conversation_states": set(contract.get("allowed_conversation_states", [])) == CONVERSATIONAL_STATES,
        "required_visible_regions": set(contract.get("required_visible_regions", [])) == REQUIRED_VISIBLE_REGIONS,
        "primary_cta_count": contract.get("primary_cta_count") == 1,
        "workflow_state_source": contract.get("workflow_state_source") == "backend_workflow_state",
        "backend_authoritative": contract.get("backend_authoritative") is True,
        "buildless_shell_contract_enabled": contract.get("buildless_shell_contract_enabled") is (contract.get("status") == "ready"),
        "atlas_next_preview_optional": contract.get("atlas_next_preview_optional") is True,
        "default_root_ui": contract.get("default_root_ui") == "ui.html",
        "default_route_promotion_allowed": contract.get("default_route_promotion_allowed") is False,
        "self_improvement_requires_backend_gates": contract.get("self_improvement_requires_backend_gates") is True,
        "shell_contract_artifact_only": contract.get("shell_contract_artifact_only") is True,
    }
    invariants.update({key: contract.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return contract


def write_conversational_shell_contract(*, contract: dict[str, Any], destination: str | Path) -> Path:
    validated = validate_conversational_shell_contract(contract)
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_conversational_shell_contract(*, manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    return validate_conversational_shell_contract(json.loads(path.read_text(encoding="utf-8")))


def _contract_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"conversational_shell_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
