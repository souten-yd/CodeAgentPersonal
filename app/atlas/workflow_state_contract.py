from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.atlas.level1_guarded_execution import Level1GuardedExecutionSkeleton

_MANIFEST_PATH = Path(__file__).parent.parent.parent / "docs" / "atlas_automation_phase_manifest.json"


def _read_manifest_field(key: str, fallback: Any) -> Any:
    try:
        with _MANIFEST_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data[key]
    except Exception:
        return fallback

_PRIMARY_REASON = "Metadata only. Execution remains in guarded backend/manual flow."
_ACTION_REASON = "Metadata only. This endpoint never executes actions."


def normalize_read_only_available_actions(actions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(actions or []):
        item = raw if isinstance(raw, dict) else {}
        action_id = str(item.get("id") or item.get("action_id") or f"action_{index + 1}")
        label = str(item.get("label") or item.get("title") or action_id)
        kind = str(item.get("kind") or "read_only")
        normalized.append(
            {
                "id": action_id,
                "label": label,
                "kind": kind,
                "read_only": True,
                "enabled": False,
                "requires_confirmation": True,
                "requires_dry_run": True,
                "reason": _ACTION_REASON,
            }
        )
    return normalized


def _coerce_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()][:8]


def _optional_text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _build_guarded_execution_review() -> dict[str, Any]:
    contract = Level1GuardedExecutionSkeleton.build_disabled_level1_contract()
    gate_source_map = contract.get("gate_source_map") if isinstance(contract.get("gate_source_map"), list) else []
    review_items = []
    for index, raw in enumerate(gate_source_map[:8]):
        item = raw if isinstance(raw, dict) else {}
        review_items.append(
            {
                "label": str(item.get("label") or item.get("gate_id") or f"Gate {index + 1}"),
                "ready": bool(item.get("evidence_available", False)),
                "source": str(item.get("source") or item.get("owner") or "backend metadata"),
            }
        )
    blockers = contract.get("blockers") if isinstance(contract.get("blockers"), list) else []
    blocked_reasons = []
    for raw in blockers[:6]:
        item = raw if isinstance(raw, dict) else {}
        gate = str(item.get("gate") or "guarded_execution_gate")
        blocker = str(item.get("blocker") or "missing evidence")
        blocked_reasons.append(f"{gate}: {blocker}")
    return {
        "checkpoint": "PR-ATLAS-SCALE-126",
        "display_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "callable_execution_route_enabled": False,
        "execution_enabled": False,
        "approval_action_enabled": False,
        "dry_run_action_enabled": False,
        "execute_action_enabled": False,
        "apply_action_enabled": False,
        "verify_action_enabled": False,
        "rollback_action_enabled": False,
        "retry_continue_action_enabled": False,
        "requires_dry_run": True,
        "requires_approval": True,
        "requires_runtime_transition": True,
        "endpoint_contract_status": "disabled_metadata_only",
        "review_items": review_items,
        "blocked_reasons": blocked_reasons,
    }


def _build_practical_loop_metadata(
    *,
    metadata_payload: dict[str, Any],
    artifacts_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build UI-safe practical loop progress metadata without execution authority."""

    verification_state = _optional_text(metadata_payload.get("verification_state"), "waiting_for_backend_checks")
    if bool(artifacts_payload.get("dry_run", False)):
        verification_state = _optional_text(metadata_payload.get("verification_state"), "dry_run_metadata_available")
    return {
        "schema_version": "atlas.practical_autonomous_dev_loop.v1",
        "status": _optional_text(metadata_payload.get("practical_loop_status"), "metadata_only"),
        "bounded_loop": bool(metadata_payload.get("bounded_loop", artifacts_payload.get("loop_bound", False))),
        "max_iterations": _coerce_non_negative_int(metadata_payload.get("max_iterations")),
        "current_iteration": _coerce_non_negative_int(metadata_payload.get("current_iteration")),
        "allowed_actions_enforced": True,
        "stop_condition": _optional_text(metadata_payload.get("stop_condition"), "manual_review_or_backend_gate"),
        "changed_files_count": _coerce_non_negative_int(metadata_payload.get("patch_candidate_count")),
        "verification_state": verification_state,
        "recovery_state": _optional_text(metadata_payload.get("recovery_state"), "unknown"),
        "draft_pr_state": _optional_text(metadata_payload.get("draft_pr_state"), "not_prepared"),
        "latest_loop_run_id": metadata_payload.get("latest_loop_run_id"),
        "latest_recovery_run_id": metadata_payload.get("latest_recovery_run_id"),
        "latest_draft_pr_artifact_id": metadata_payload.get("latest_draft_pr_artifact_id"),
        "execution_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "self_apply_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "vue_authoritative": False,
        "advisory_only": True,
    }


def build_read_only_workflow_state(
    *,
    goal: str,
    project_path: str,
    phase: str,
    status: str,
    primary_cta_label: str,
    available_actions: list[dict[str, Any]] | None = None,
    artifacts: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    workflow_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts_payload = artifacts or {}
    metadata_payload = workflow_metadata or {}
    patch_transaction_available = bool(
        metadata_payload.get("patch_transaction_available", artifacts_payload.get("transaction", False))
    )
    practical_loop_metadata = _build_practical_loop_metadata(
        metadata_payload=metadata_payload,
        artifacts_payload=artifacts_payload,
    )
    return {
        "schema_version": "atlas.workflow_state.v1",
        "contract": "read_only_workflow_state",
        "contract_scope": "vue_next_preview_read_only",
        "source": "backend_contract",
        "runtime_level": "level_0_manual_only",
        "preview_runtime_level": "level_0_manual_only",
        "canonical_runtime_level": _read_manifest_field("current_level", "level_8_fully_autonomous_code_agent"),
        "canonical_autonomous_execution_enabled": _read_manifest_field("autonomous_execution_enabled", True),
        "backend_workflow_state_authoritative": True,
        "vue_source_of_truth": False,
        "vue_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "level1_execution_enabled": False,
        "level1_disabled_backend_skeleton": Level1GuardedExecutionSkeleton.build_disabled_level1_contract(),
        "goal": goal,
        "project_path": project_path,
        "phase": phase,
        "status": status,
        "primary_cta": {
            "label": primary_cta_label,
            "state": "read_only",
            "enabled": False,
            "read_only": True,
            "reason": _PRIMARY_REASON,
        },
        "available_actions": normalize_read_only_available_actions(available_actions),
        "safety": {
            "dry_run_first_preserved": True,
            "execute_one_action_preserved": True,
            "manual_only": True,
            "mutation_endpoints_enabled": False,
            "automatic_execution_enabled": False,
            "automatic_verification_enabled": False,
            "automatic_patch_generation_enabled": False,
            "automatic_patch_apply_enabled": False,
            "automatic_rollback_enabled": False,
            "automatic_retry_enabled": False,
            "execute_all_enabled": False,
            "auto_continue_enabled": False,
        },
        "artifacts": {
            "snapshot": bool(artifacts_payload.get("snapshot", False)),
            "transaction": bool(artifacts_payload.get("transaction", False)),
            "risk": bool(artifacts_payload.get("risk", False)),
            "allowlist": bool(artifacts_payload.get("allowlist", False)),
            "dry_run": bool(artifacts_payload.get("dry_run", False)),
            "rollback": bool(artifacts_payload.get("rollback", False)),
            "artifact_capture": bool(artifacts_payload.get("artifact_capture", False)),
            "stop": bool(artifacts_payload.get("stop", False)),
            "loop_bound": bool(artifacts_payload.get("loop_bound", False)),
            "remote_git": bool(artifacts_payload.get("remote_git", False)),
            "self_improvement": bool(artifacts_payload.get("self_improvement", False)),
            "rollup": bool(artifacts_payload.get("rollup", False)),
        },
        "patch_transaction_metadata": {
            "available": patch_transaction_available,
            "transaction_id": metadata_payload.get("latest_patch_transaction_id"),
            "candidate_count": _coerce_non_negative_int(metadata_payload.get("patch_candidate_count")),
            "source": metadata_payload.get("patch_transaction_source", "backend_contract_metadata_only"),
            "preview_status": metadata_payload.get("patch_transaction_preview_status", "missing"),
            "risk_class": metadata_payload.get("patch_transaction_risk_class", "unknown"),
            "rollback_ready": bool(metadata_payload.get("patch_transaction_rollback_ready", False)),
            "warnings": _coerce_string_list(metadata_payload.get("patch_transaction_warnings")),
            "generation_enabled": False,
            "apply_enabled": False,
            "safe_apply_enabled": False,
            "verification_enabled": False,
            "rollback_enabled": False,
            "advisory_only": True,
        },
        "practical_loop_metadata": practical_loop_metadata,
        "guarded_execution_review": _build_guarded_execution_review(),
        "diagnostics": {
            "static_mount_deferred": False,
            "route_mounted": True,
            "route_path": "/atlas-next",
            "route_default": False,
            "route_guarded": True,
            "dist_backed": True,
            "fail_closed": True,
            "diagnostics_endpoint": "/api/atlas/vue-next-preview/diagnostics",
            "preview_health": "observable_fail_closed",
            "backend_contract_ready": True,
            "warnings": list(warnings or []),
        },
        "workflow_state_metadata": {
            "latest_pool_id": metadata_payload.get("latest_pool_id"),
            "latest_run_id": metadata_payload.get("latest_run_id"),
            "latest_plan_id": metadata_payload.get("latest_plan_id"),
            "latest_requirement_id": metadata_payload.get("latest_requirement_id"),
            "current_phase": metadata_payload.get("current_phase"),
            "latest_status": metadata_payload.get("latest_status"),
            "continuation_state": metadata_payload.get("continuation_state"),
            "recovery_state": metadata_payload.get("recovery_state"),
            "plan_pool_available": bool(metadata_payload.get("plan_pool_available", False)),
            "active_plan_available": bool(metadata_payload.get("active_plan_available", False)),
            "last_report_available": bool(metadata_payload.get("last_report_available", False)),
            "last_error_summary": metadata_payload.get("last_error_summary"),
            "last_updated_at": metadata_payload.get("last_updated_at"),
            "data_freshness": metadata_payload.get("data_freshness", "unknown"),
            "source_detail": metadata_payload.get("source_detail", "backend_contract_metadata_only"),
            "workflow_snapshot_available": bool(metadata_payload.get("workflow_snapshot_available", False)),
        },
    }


def summarize_workflow_state_contract(payload: dict[str, Any]) -> dict[str, Any]:
    practical_loop = payload.get("practical_loop_metadata") or {}
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "contract": str(payload.get("contract", "")),
        "runtime_level": str(payload.get("runtime_level", "level_0_manual_only")),
        "manual_only": bool((payload.get("safety") or {}).get("manual_only", True)),
        "available_action_count": len(payload.get("available_actions") or []),
        "backend_contract_ready": bool((payload.get("diagnostics") or {}).get("backend_contract_ready", False)),
        "practical_loop_status": str(practical_loop.get("status", "metadata_only")),
        "practical_loop_advisory_only": bool(practical_loop.get("advisory_only", True)),
    }
