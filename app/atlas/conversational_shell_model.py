from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.atlas.conversational_shell_contract import (
    CURRENT_RUNTIME_LEVEL,
    NEXT_REQUIRED_PR as CONTRACT_NEXT_REQUIRED_PR,
    REQUIRED_VISIBLE_REGIONS,
    SCHEMA_VERSION as CONTRACT_SCHEMA_VERSION,
    STATE_IDLE,
    TRACK_PR as CONTRACT_TRACK_PR,
    WORK_TARGET_MODES,
    WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
    WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    validate_conversational_shell_contract,
)

SCHEMA_VERSION = "atlas.conversational_shell_model.v1"
TRACK_PR = "PR-ATLAS-SCALE-152"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-153"

_PRIMARY_CTA_BY_STATE = {
    STATE_IDLE: "Start Atlas",
    "understanding_goal": "Clarify Requirement",
    "planning": "Review Plan",
    "needs_scope_confirmation": "Confirm Scope",
    "previewing_changes": "Review Preview",
    "awaiting_approval": "Review Approval",
    "running_dry_run": "View Dry-run",
    "applying_candidate": "View Candidate",
    "verifying_candidate": "View Verification",
    "promoting_candidate": "View Promotion Gate",
    "draft_pr_ready": "Review Draft PR",
    "blocked": "Review Blocker",
    "recoverable_failure": "Review Recovery",
    "recovered": "Continue Atlas",
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


def create_conversational_shell_model(
    *,
    contract: dict[str, Any],
    conversation_messages: list[dict[str, Any]] | None = None,
    changed_files: list[str] | None = None,
    verification_summary: dict[str, Any] | None = None,
    recovery_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validated_contract = validate_conversational_shell_contract(deepcopy(contract))
    state = str(validated_contract["conversation_state"])
    raw_mode = str(validated_contract["work_target_mode"])
    mode = raw_mode if raw_mode in WORK_TARGET_MODES else WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR
    messages = [_normalize_message(message) for message in conversation_messages or []]
    files = [_normalize_repo_path(path) for path in changed_files or []]

    model = {
        "schema_version": SCHEMA_VERSION,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "source_contract_schema_version": validated_contract["schema_version"],
        "source_contract_track_pr": validated_contract["track_pr"],
        "source_contract_next_required_pr": validated_contract["next_required_pr"],
        "runtime_level": CURRENT_RUNTIME_LEVEL,
        "status": "ready" if validated_contract["status"] == "ready" else "blocked",
        "blocking_reasons": list(validated_contract.get("blocking_reasons", [])),
        "backend_authoritative": True,
        "workflow_state_source": "backend_workflow_state",
        "default_root_ui": "ui.html",
        "atlas_next_preview_optional": True,
        "buildless_shell_model_enabled": validated_contract["status"] == "ready",
        "required_visible_regions": sorted(REQUIRED_VISIBLE_REGIONS),
        "conversation_transcript": {
            "region_id": "conversation_transcript",
            "messages": messages,
            "empty_state": "Describe what Atlas should build or fix.",
        },
        "goal_input": {
            "region_id": "goal_input",
            "value": validated_contract["goal"],
            "placeholder": "Tell Atlas the requirement, constraints, and desired result.",
        },
        "current_phase_card": {
            "region_id": "current_phase_card",
            "phase": validated_contract["current_phase"],
            "conversation_state": state,
            "runtime_level": CURRENT_RUNTIME_LEVEL,
        },
        "next_action_card": {
            "region_id": "next_action_card",
            "next_action": validated_contract["next_action"],
            "primary_cta": _primary_cta_for_state(state),
        },
        "safety_profile_badge": {
            "region_id": "safety_profile_badge",
            "selected_safety_profile": validated_contract["selected_safety_profile"],
            "authority": "backend_only",
        },
        "work_target_mode_selector": {
            "region_id": "work_target_mode_selector",
            "selected": mode,
            "options": _work_target_options(mode),
            "backend_owned": True,
            "authorizes_self_improvement": False,
        },
        "changed_files_summary": {
            "region_id": "changed_files_summary",
            "files": files,
            "count": len(files),
        },
        "verification_summary": {
            "region_id": "verification_summary",
            **_normalize_summary(verification_summary, default_status="not_run"),
        },
        "recovery_status": {
            "region_id": "recovery_status",
            **_normalize_summary(recovery_summary, default_status="not_required"),
        },
        "primary_cta": {
            "region_id": "primary_cta",
            "label": _primary_cta_for_state(state),
            "enabled": validated_contract["status"] == "ready",
            "intent_only": True,
        },
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
    }
    return validate_conversational_shell_model(model)


def validate_conversational_shell_model(model: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "source_contract_schema_version",
        "source_contract_track_pr",
        "source_contract_next_required_pr",
        "runtime_level",
        "status",
        "backend_authoritative",
        "workflow_state_source",
        "default_root_ui",
        "atlas_next_preview_optional",
        "buildless_shell_model_enabled",
        "required_visible_regions",
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
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in model]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    is_blocked = model.get("status") == "blocked"
    regions = set(model.get("required_visible_regions", []))
    selector = dict(model.get("work_target_mode_selector", {}))
    primary_cta = dict(model.get("primary_cta", {}))
    invariants = {
        "schema_version": model.get("schema_version") == SCHEMA_VERSION,
        "track_pr": model.get("track_pr") == TRACK_PR,
        "next_required_pr": model.get("next_required_pr") == NEXT_REQUIRED_PR,
        "source_contract_schema_version": model.get("source_contract_schema_version") == CONTRACT_SCHEMA_VERSION,
        "source_contract_track_pr": model.get("source_contract_track_pr") == CONTRACT_TRACK_PR,
        "source_contract_next_required_pr": model.get("source_contract_next_required_pr") == CONTRACT_NEXT_REQUIRED_PR,
        "runtime_level": model.get("runtime_level") == CURRENT_RUNTIME_LEVEL,
        "status": model.get("status") in {"ready", "blocked"},
        "blocking_reasons": not is_blocked or bool(model.get("blocking_reasons")),
        "backend_authoritative": model.get("backend_authoritative") is True,
        "workflow_state_source": model.get("workflow_state_source") == "backend_workflow_state",
        "default_root_ui": model.get("default_root_ui") == "ui.html",
        "atlas_next_preview_optional": model.get("atlas_next_preview_optional") is True,
        "buildless_shell_model_enabled": model.get("buildless_shell_model_enabled") is (model.get("status") == "ready"),
        "required_visible_regions": regions == REQUIRED_VISIBLE_REGIONS,
        "visible_region_objects": all(_region_has_id(model, region) for region in REQUIRED_VISIBLE_REGIONS),
        "primary_cta": primary_cta.get("region_id") == "primary_cta" and primary_cta.get("intent_only") is True,
        "work_target_mode_selector": _selector_is_valid(selector),
    }
    invariants.update({key: model.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return model


def _work_target_options(selected: str) -> list[dict[str, Any]]:
    return [
        {
            "value": WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
            "label": "Software development / repair",
            "selected": selected == WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
            "requires_backend_gates": False,
            "authorizes_execution": False,
            "authorizes_self_improvement": False,
        },
        {
            "value": WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
            "label": "Atlas platform self-improvement",
            "selected": selected == WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
            "requires_backend_gates": True,
            "authorizes_execution": False,
            "authorizes_self_improvement": False,
        },
    ]


def _primary_cta_for_state(state: str) -> str:
    return _PRIMARY_CTA_BY_STATE.get(state, "Start Atlas")


def _normalize_message(message: dict[str, Any]) -> dict[str, str]:
    role = str(message.get("role", "system")).strip() or "system"
    content = str(message.get("content", "")).strip()
    return {"role": role, "content": content}


def _normalize_repo_path(path: str) -> str:
    normalized = str(path).strip().replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or ":" in normalized.split("/", 1)[0]:
        raise ValueError("changed_file_must_be_repo_relative")
    return normalized


def _normalize_summary(summary: dict[str, Any] | None, *, default_status: str) -> dict[str, Any]:
    data = dict(summary or {})
    return {
        "status": str(data.get("status", default_status)),
        "summary": str(data.get("summary", "")),
        "evidence_ref": str(data.get("evidence_ref", "")),
    }


def _region_has_id(model: dict[str, Any], region: str) -> bool:
    value = model.get(region)
    return isinstance(value, dict) and value.get("region_id") == region


def _selector_is_valid(selector: dict[str, Any]) -> bool:
    options = list(selector.get("options", []))
    values = {option.get("value") for option in options}
    selected = selector.get("selected")
    return (
        selector.get("region_id") == "work_target_mode_selector"
        and selector.get("backend_owned") is True
        and selector.get("authorizes_self_improvement") is False
        and selected in WORK_TARGET_MODES
        and values == WORK_TARGET_MODES
        and sum(1 for option in options if option.get("selected")) == 1
        and all(option.get("authorizes_execution") is False for option in options)
        and all(option.get("authorizes_self_improvement") is False for option in options)
    )
