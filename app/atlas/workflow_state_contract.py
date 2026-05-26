from __future__ import annotations

from typing import Any

from app.atlas.level1_guarded_execution import Level1GuardedExecutionSkeleton

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
    return {
        "schema_version": "atlas.workflow_state.v1",
        "contract": "read_only_workflow_state",
        "source": "backend_contract",
        "runtime_level": "level_0_manual_only",
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
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "contract": str(payload.get("contract", "")),
        "runtime_level": str(payload.get("runtime_level", "level_0_manual_only")),
        "manual_only": bool((payload.get("safety") or {}).get("manual_only", True)),
        "available_action_count": len(payload.get("available_actions") or []),
        "backend_contract_ready": bool((payload.get("diagnostics") or {}).get("backend_contract_ready", False)),
    }
