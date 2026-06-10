from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest, AtlasAutoVerificationResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_verification_gate_schema import AtlasVerificationRequest, AtlasVerificationResult
from agent.project_intelligence.adapters.atlas_verification import AtlasVerificationBridge
from agent.project_intelligence.checkpoint import Checkpoint
from agent.project_intelligence.contracts import (
    ProjectIdentity,
    RuntimeObservationRecord,
    VerificationResultRequest,
)
from agent.project_twin.project_identity import compute_working_tree_hash


VerificationRequest = AtlasVerificationRequest | AtlasAutoVerificationRequest
VerificationResult = AtlasVerificationResult | AtlasAutoVerificationResult


def record_project_intelligence_verification(
    *,
    project_intelligence: Any,
    checkpoint_bridge: AtlasVerificationBridge,
    pool: AtlasPlanPool,
    item: AtlasPlanItem,
    request: VerificationRequest,
    result: VerificationResult,
    source: str,
) -> dict[str, Any]:
    """Record canonical Atlas verification output with Project Intelligence.

    Atlas verification remains the authority. This adapter only mirrors persisted
    verification evidence into Project Intelligence, writes an idempotent checkpoint,
    and returns metadata for existing recovery/continuation surfaces.
    """
    if project_intelligence is None:
        return {}

    correlation_id = _correlation_id(pool, item, request, result, source)
    prior = ((item.metadata or {}).get("verification") or {}).get("project_intelligence_verification") or {}
    if prior.get("correlation_id") == correlation_id and prior.get("status") == "recorded":
        return {**prior, "idempotent_replay": True}

    project = _project_identity(pool, request)
    status = str(getattr(result, "status", "") or "").lower()
    observation = _observation(project, pool, item, request, result, status=status, source=source)
    refs = _revision_refs(pool, item, request, result, project)
    try:
        pi_result = project_intelligence.record_verification_result(
            VerificationResultRequest(
                project=project,
                plan_pool_id=pool.pool_id,
                plan_item_id=item.item_id,
                observations=[observation],
                blueprint_revision_id=refs["blueprint_revision_id"],
                actual_twin_revision_id=refs["actual_twin_revision_id"],
                source_revision=refs["source_revision"],
                plan_pool_revision=refs["plan_pool_revision"],
                correlation_id=correlation_id,
            )
        )
        checkpoint = Checkpoint(
            project_id=project.project_id,
            workspace_id=project.workspace_id,
            plan_pool_id=pool.pool_id,
            plan_item_id=item.item_id,
            requirement_revision=refs["requirement_revision_id"],
            blueprint_revision=refs["blueprint_revision_id"],
            actual_twin_revision=pi_result.twin_revision_id or refs["actual_twin_revision_id"],
            convergence_report_id=pi_result.convergence_report_id,
            plan_pool_revision=refs["plan_pool_revision"],
            last_successful_evidence=[observation.observation_id] if observation.result == "passed" else [],
            rollout_mode=_mode_for_phase(project_intelligence, "verification"),
            working_tree_hash=project.working_tree_hash,
        )
        checkpoint_out = checkpoint_bridge.record_verification(
            checkpoint=checkpoint,
            observations=[observation],
            idempotency_key=correlation_id,
        )
        route = _route_decision(status, dict(pi_result.convergence_decision or {}))
        return {
            "status": "recorded",
            "mode": _mode_for_phase(project_intelligence, "verification"),
            "source": source,
            "correlation_id": correlation_id,
            "accepted": bool(pi_result.accepted),
            "twin_revision_id": pi_result.twin_revision_id,
            "convergence_report_id": pi_result.convergence_report_id,
            "convergence_decision": dict(pi_result.convergence_decision or {}),
            "checkpoint_id": checkpoint_out.checkpoint_id,
            "checkpoint_duplicate": bool(checkpoint_out.duplicate),
            "rollback_base_revision": checkpoint_out.rollback_base_revision,
            "last_successful_evidence": list(checkpoint_out.last_successful_evidence),
            "rollup": _dump_model(checkpoint_out.rollup),
            "decision_route": route,
            "revisions": refs,
            "diagnostics": [
                d.model_dump() if hasattr(d, "model_dump") else dict(d)
                for d in getattr(pi_result, "diagnostics", [])
            ] + list(checkpoint_out.diagnostics),
        }
    except Exception as exc:  # noqa: BLE001 - verification result remains canonical.
        return {
            "status": "degraded_retry_required",
            "mode": _mode_for_phase(project_intelligence, "verification"),
            "source": source,
            "correlation_id": correlation_id,
            "error_kind": exc.__class__.__name__,
            "diagnostics": [str(exc)[:300]],
            "revisions": refs,
        }


def _mode_for_phase(project_intelligence: Any, phase: str) -> str:
    rollout = getattr(project_intelligence, "rollout", None)
    mode = getattr(rollout, "mode_for_phase", None)
    if callable(mode):
        return str(mode(phase))
    return "off"


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _project_identity(pool: AtlasPlanPool, request: VerificationRequest) -> ProjectIdentity:
    project_path = str(pool.project_path or "")
    working_tree_hash = ""
    if project_path:
        try:
            root = Path(project_path)
            if root.is_dir():
                working_tree_hash = compute_working_tree_hash(root)
        except Exception:
            working_tree_hash = ""
    return ProjectIdentity(
        project_id=str(pool.project_name or (pool.metadata or {}).get("project_id") or "atlas"),
        workspace_id=str(getattr(request, "workspace_id", "") or (pool.metadata or {}).get("workspace_id") or "default"),
        project_path=project_path,
        source_revision=str((pool.metadata or {}).get("source_revision_id") or "") or None,
        working_tree_hash=working_tree_hash,
    )


def _correlation_id(
    pool: AtlasPlanPool,
    item: AtlasPlanItem,
    request: VerificationRequest,
    result: VerificationResult,
    source: str,
) -> str:
    run_id = str(getattr(request, "run_id", "") or getattr(result, "run_id", "") or "")
    return run_id or f"{source}:verification:{pool.pool_id}:{item.item_id}:{getattr(result, 'status', '')}"


def _observation(
    project: ProjectIdentity,
    pool: AtlasPlanPool,
    item: AtlasPlanItem,
    request: VerificationRequest,
    result: VerificationResult,
    *,
    status: str,
    source: str,
) -> RuntimeObservationRecord:
    refs = _evidence_refs(result)
    subject_refs = [f"planitem://{item.item_id}", *[p if "://" in p else f"file://{p}" for p in item.target_files]]
    if status == "passed":
        observation_result = "passed"
    elif status in {"failed"}:
        observation_result = "failed"
    else:
        observation_result = "unavailable"
    return RuntimeObservationRecord(
        observation_id=_correlation_id(pool, item, request, result, source),
        project_id=project.project_id,
        workspace_id=project.workspace_id,
        run_id=str(getattr(request, "run_id", "") or ""),
        collector=f"atlas_{source}_verification",
        collector_version="pir12.v1",
        observation_type="verification_result",
        subject_refs=subject_refs,
        source_revision=_revision_refs(pool, item, request, result, project)["source_revision"],
        result=observation_result,
        summary=f"{source} verification {status or 'unknown'}",
        evidence_refs=refs,
        payload_ref=refs[0] if refs else None,
    )


def _evidence_refs(result: VerificationResult) -> list[str]:
    metadata = dict(getattr(result, "metadata", {}) or {})
    refs: list[str] = []
    for key in ("verification_record_json", "verification_record_md"):
        value = str(metadata.get(key) or "")
        if value:
            refs.append(value if "://" in value else f"file://{value}")
    command_id = str(getattr(result, "command_id", "") or "")
    if command_id:
        refs.append(f"verification_command://{command_id}")
    run_id = str(getattr(result, "run_id", "") or "")
    if run_id:
        refs.append(f"verification://{run_id}")
    return list(dict.fromkeys(refs))


def _revision_refs(
    pool: AtlasPlanPool,
    item: AtlasPlanItem,
    request: VerificationRequest,
    result: VerificationResult,
    project: ProjectIdentity,
) -> dict[str, str | None]:
    metadata = dict(getattr(request, "metadata", {}) or {})
    item_meta = dict(item.metadata or {})
    safe_apply = dict(item_meta.get("safe_apply") or {})
    pi_apply = dict(safe_apply.get("project_intelligence_apply") or {})
    pool_meta = dict(pool.metadata or {})
    source_revision = (
        metadata.get("source_revision")
        or safe_apply.get("new_source_revision")
        or safe_apply.get("source_revision")
        or pool_meta.get("source_revision_id")
        or project.source_revision
    )
    return {
        "requirement_revision_id": str(pool_meta.get("requirement_revision_id") or pool.linked_requirement_id or "") or None,
        "blueprint_revision_id": str(item_meta.get("blueprint_revision_id") or pool_meta.get("blueprint_revision_id") or "") or None,
        "actual_twin_revision_id": str(
            pi_apply.get("twin_revision_id")
            or metadata.get("actual_twin_revision_id")
            or pool_meta.get("actual_twin_revision_id")
            or ""
        ) or None,
        "source_revision": str(source_revision or "") or None,
        "apply_revision": str(pi_apply.get("correlation_id") or safe_apply.get("change_snapshot_id") or "") or None,
        "plan_pool_revision": str(pool_meta.get("plan_revision_id") or pool.updated_at or "") or None,
    }


def _route_decision(status: str, decision: dict[str, Any]) -> dict[str, Any]:
    action = str(decision.get("action") or "")
    if status == "failed":
        return {
            "action": "repair_current_item",
            "existing_services": ["self_correction", "bounded_retry", "continuation"],
            "reason": "verification_failed",
        }
    if status in {"blocked", "skipped"}:
        return {
            "action": "request_critical_decision",
            "existing_services": ["critical_decision", "continuation"],
            "reason": "verification_unavailable",
        }
    if action in {"repair_current_item", "replan_downstream", "revise_blueprint", "request_critical_decision", "halt_unsafe", "complete"}:
        service_map = {
            "repair_current_item": ["self_correction", "bounded_retry"],
            "replan_downstream": ["replanning", "continuation"],
            "revise_blueprint": ["blueprint_revision", "critical_decision"],
            "request_critical_decision": ["critical_decision"],
            "halt_unsafe": ["failure_stop", "continuation"],
            "complete": ["continuation"],
        }
        return {"action": action, "existing_services": service_map[action], "reason": "convergence_decision"}
    return {"action": "continue", "existing_services": ["continuation"], "reason": "verification_passed"}
