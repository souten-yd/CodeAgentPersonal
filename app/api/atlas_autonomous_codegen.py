from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.api.atlas_multi_item_autopilot import _service as _build_multi_item_service, _validate_id
from agent.atlas_clarification_execution_blocker import clarification_execution_block_reasons
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

router = APIRouter(prefix="/api/atlas/autonomous-codegen", tags=["atlas-autonomous-codegen"])


def _orchestrator_service(request: Request | None, workspace_id: str, pool_id: str) -> AtlasAutonomousCodegenOrchestratorService:
    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root)
    journal = AtlasJournal(root, workspace_id=workspace_id or "default")
    # Patch generation needs the app's LLM json fn; None in tests/offline -> the proposal yields no
    # content and Phase 3 honestly skips uncontented items rather than reporting fake success.
    llm_json_fn = getattr(getattr(getattr(request, "app", None), "state", None), "atlas_llm_json_fn", None)
    patch_proposal_service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm_json_fn)
    # Reuse the multi-item autopilot wiring verbatim so the apply phase inherits the same executor,
    # gates and full_auto relaxation (single source of truth).
    multi_item_service = _build_multi_item_service(request, workspace_id, pool_id=pool_id)
    return AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=patch_proposal_service,
        multi_item_autopilot_service=multi_item_service,
        data_root=root,
    )


@router.post("/run")
def run(payload: AtlasAutonomousCodegenRequest, request: Request):
    payload.pool_id = _validate_id(payload.pool_id, "pool_id")
    if payload.run_id:
        payload.run_id = _validate_id(payload.run_id, "run_id")
    payload.item_ids = [_validate_id(v, "item_id") for v in (payload.item_ids or [])]
    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root)
    try:
        pool = storage.load_pool(payload.pool_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"error": "pool_not_found", "reason": f"pool_not_found:{payload.pool_id}"}) from exc
    clarification_blocks = clarification_execution_block_reasons(pool)
    if clarification_blocks:
        pending_tokens = {
            "clarification_required",
            "clarification_pending_questions",
            "clarification_questions_unanswered",
        }
        pending = any(reason in pending_tokens for reason in clarification_blocks)
        return {
            "pool_id": payload.pool_id,
            "run_id": payload.run_id,
            "orchestrator_run_id": "",
            "phase": "needs_scope_confirmation" if pending else "revising_plan_from_clarification",
            "status": "blocked_safety_review",
            "generated_count": 0,
            "skipped_generation_count": 0,
            "proposal_results": [],
            "autopilot_result": {},
            "stop_reason": "clarification_pending" if pending else "clarification_revision_gate_rerun_required",
            "warnings": clarification_blocks,
            "errors": [],
            "metadata": {
                "clarification_execution_blocked": True,
                "blocked_reasons": clarification_blocks,
                "plan_pool": pool.model_dump(),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    try:
        return _orchestrator_service(request, payload.workspace_id, pool_id=payload.pool_id).run(payload).model_dump()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": "autonomous_codegen_failed", "reason": f"{exc.__class__.__name__}: {exc}"[:300]},
        ) from exc


@router.post("/start")
def start(payload: AtlasAutonomousCodegenRequest, request: Request):
    return run(payload, request)


@router.get("/results/{pool_id}/{orchestrator_run_id}")
def read_result(pool_id: str, orchestrator_run_id: str, request: Request):
    pool_id = _validate_id(pool_id, "pool_id")
    orchestrator_run_id = _validate_id(orchestrator_run_id, "orchestrator_run_id")
    path = Path(resolve_atlas_ca_data_root(request)) / "atlas" / "autonomous_codegen" / pool_id / f"{orchestrator_run_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "autonomous_codegen_result_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/status/{pool_id}/{orchestrator_run_id}")
def read_status(pool_id: str, orchestrator_run_id: str, request: Request):
    payload = read_result(pool_id, orchestrator_run_id, request)
    return _normalized_status(payload)


def _normalized_status(payload: dict) -> dict:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    preflight = metadata.get("preflight") if isinstance(metadata.get("preflight"), dict) else {}
    autopilot = payload.get("autopilot_result") if isinstance(payload.get("autopilot_result"), dict) else {}
    workspace_evidence = metadata.get("workspace_evidence") if isinstance(metadata.get("workspace_evidence"), dict) else {}
    recovery_evidence = metadata.get("recovery_evidence") if isinstance(metadata.get("recovery_evidence"), dict) else {}
    draft_pr_readiness = metadata.get("draft_pr_readiness") if isinstance(metadata.get("draft_pr_readiness"), dict) else {}
    draft_pr_artifact = metadata.get("draft_pr_artifact") if isinstance(metadata.get("draft_pr_artifact"), dict) else {}
    ci_failure_evidence = metadata.get("ci_failure_evidence") if isinstance(metadata.get("ci_failure_evidence"), dict) else {}
    ci_repair_plan = metadata.get("ci_repair_plan") if isinstance(metadata.get("ci_repair_plan"), dict) else {}
    phase = str(payload.get("phase") or "")
    status = str(payload.get("status") or "")
    stop_reason = str(payload.get("stop_reason") or "")
    changed_files = list(metadata.get("changed_files") or [])
    item_results = list(autopilot.get("item_results") or [])
    warnings = _unique(
        list(payload.get("warnings") or [])
        + list(preflight.get("warnings") or [])
        + list(workspace_evidence.get("warnings") or [])
        + list(recovery_evidence.get("warnings") or [])
    )
    decision_targets = _decision_targets(phase=phase, status=status, stop_reason=stop_reason, metadata=metadata)
    next_action = _next_action(payload)
    return {
        "pool_id": payload.get("pool_id", ""),
        "run_id": payload.get("run_id", ""),
        "orchestrator_run_id": payload.get("orchestrator_run_id", ""),
        "status": status,
        "automation_state": _automation_state(status),
        "current_phase": phase,
        "next_action": next_action,
        "active_profile": {
            "profile": preflight.get("normalized_profile", "review_only"),
            "preset": metadata.get("selected_preset", ""),
            "envelope_id": preflight.get("envelope_id", ""),
            "runtime_level": _runtime_level(str(preflight.get("normalized_profile") or "review_only")),
        },
        "requirement_summary": payload.get("user_requirement", "") or metadata.get("user_requirement", ""),
        "plan_summary": {
            "processed_count": autopilot.get("processed_count", metadata.get("processed_count", 0)),
            "completed_count": autopilot.get("completed_count", metadata.get("completed_count", 0)),
            "failed_count": autopilot.get("failed_count", metadata.get("failed_count", 0)),
            "blocked_count": autopilot.get("blocked_count", metadata.get("blocked_count", 0)),
        },
        "decision_targets": decision_targets,
        "evidence_summary": {
            "changed_files": changed_files,
            "verification": _verification_summary(item_results),
            "verification_failure_summary": metadata.get("verification_failure_summary") or {},
            "repair_plan": metadata.get("repair_plan") or {},
            "ci_failure_evidence": ci_failure_evidence,
            "ci_repair_plan": ci_repair_plan,
            "post_ci_repair_verification_required": bool(metadata.get("post_ci_repair_verification_required")),
            "repair_attempts": _repair_summary(item_results, metadata),
            "final_summary": {
                "status": status,
                "stop_reason": stop_reason,
                "draft_pr_ready": bool(draft_pr_readiness.get("ready")),
            },
            "draft_pr": {
                "ready": bool(draft_pr_readiness.get("ready")),
                "artifact_path": draft_pr_readiness.get("artifact_path") or draft_pr_artifact.get("artifact_path", ""),
                "body_path": draft_pr_readiness.get("body_path") or draft_pr_artifact.get("body_path", ""),
                "draft_pr_url": draft_pr_readiness.get("draft_pr_url", ""),
            },
            "workspace": workspace_evidence,
            "recovery": {
                "status": str(
                    recovery_evidence.get("status")
                    or ((recovery_evidence.get("summary") or {}) if isinstance(recovery_evidence.get("summary"), dict) else {}).get("status", "")
                ),
                "snapshot_manifest_path": str(recovery_evidence.get("snapshot_manifest_path") or ""),
                "changed_files": list(recovery_evidence.get("changed_files") or []),
                "restore_available": bool(recovery_evidence.get("restore_available")),
                "restore_executed": bool(recovery_evidence.get("restore_executed")),
                "rollback_executed": bool(recovery_evidence.get("rollback_executed")),
                "recovery_execution_performed": bool(recovery_evidence.get("recovery_execution_performed")),
            },
        },
        "user_visible_warnings": warnings,
        "controls": _controls(status=status, phase=phase, decision_targets=decision_targets),
        "raw_json_included": False,
    }


@router.get("/latest/{pool_id}")
def read_latest(pool_id: str, request: Request):
    pool_id = _validate_id(pool_id, "pool_id")
    path = Path(resolve_atlas_ca_data_root(request)) / "atlas" / "autonomous_codegen" / pool_id / "latest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "autonomous_codegen_result_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/stop")
def stop(payload: dict, request: Request):
    pool_id = _validate_id(str(payload.get("pool_id") or ""), "pool_id")
    run_id = str(payload.get("run_id") or "")
    root = Path(resolve_atlas_ca_data_root(request)) / "atlas" / "autonomous_codegen" / pool_id
    root.mkdir(parents=True, exist_ok=True)
    marker = {
        "pool_id": pool_id,
        "run_id": run_id,
        "status": "stopped",
        "current_phase": "final_summary",
        "stop_reason": str(payload.get("reason") or "user_stop_requested"),
        "next_action": "Review stopped autonomous code-generation run.",
    }
    (root / "stop_requested.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker


@router.post("/cancel")
def cancel(payload: dict, request: Request):
    payload = {**dict(payload or {}), "reason": str((payload or {}).get("reason") or "user_cancel_requested")}
    result = stop(payload, request)
    result["status"] = "cancelled"
    result["current_phase"] = "final_summary"
    result["next_action"] = "Autonomous code-generation run cancelled by user."
    return result


def _next_action(payload: dict) -> str:
    status = str(payload.get("status") or "")
    phase = str(payload.get("phase") or "")
    if phase == "needs_scope_confirmation":
        return "Answer remaining clarification"
    if phase == "waiting_for_critical_decision":
        return "Make critical event decision"
    if status in {"stopped", "blocked_safety_review"}:
        return f"Resolve stop reason: {payload.get('stop_reason') or 'blocked'}"
    if status in {"completed", "partial"}:
        return "Review final summary and prepare draft PR artifact when allowed."
    return "Poll status or inspect the autonomous code-generation result."


def _automation_state(status: str) -> str:
    if status in {"completed", "partial"}:
        return "completed"
    if status in {"stopped", "failed", "needs_revision", "no_items"}:
        return "stopped"
    if status in {"blocked_safety_review"}:
        return "blocked"
    return "active"


def _runtime_level(profile: str) -> str:
    return {
        "review_only": "level_0_manual_only",
        "guarded_single_action": "level_1_guarded_execution",
        "supervised_bounded_auto": "level_4_self_improvement_platform",
        "autonomous_dev_agent": "level_8_fully_autonomous_code_agent",
    }.get(profile, "level_0_manual_only")


def _decision_targets(*, phase: str, status: str, stop_reason: str, metadata: dict) -> dict:
    clarification_visible = phase == "needs_scope_confirmation" or "clarification" in stop_reason
    critical_visible = phase == "waiting_for_critical_decision" or "critical" in stop_reason
    lower_impact_visible = phase == "replanning_lower_impact" or bool(metadata.get("critical_replanning"))
    return {
        "clarification": {
            "visible": clarification_visible,
            "required": clarification_visible,
            "action": "answer_clarification" if clarification_visible else "",
        },
        "critical_event": {
            "visible": critical_visible,
            "required": critical_visible,
            "actions": ["approve_critical_event", "reject_and_request_safer_alternative"] if critical_visible else [],
        },
        "lower_impact_replanning": {
            "visible": lower_impact_visible,
            "required": lower_impact_visible and status == "blocked_safety_review",
        },
    }


def _controls(*, status: str, phase: str, decision_targets: dict) -> dict:
    blocked_for_decision = bool(
        (decision_targets.get("clarification") or {}).get("required")
        or (decision_targets.get("critical_event") or {}).get("required")
    )
    return {
        "can_start": status in {"", "stopped", "failed", "needs_revision", "no_items"},
        "can_stop": status in {"running"} or phase not in {"final_summary", "completed"},
        "can_cancel": status not in {"completed", "partial"},
        "can_answer_clarification": bool((decision_targets.get("clarification") or {}).get("required")),
        "can_approve_critical_event": bool((decision_targets.get("critical_event") or {}).get("required")),
        "can_reject_critical_event": bool((decision_targets.get("critical_event") or {}).get("required")),
        "can_edit_scope": status in {"blocked_safety_review", "needs_revision"} or blocked_for_decision,
        "can_execute": False,
        "can_continue": not blocked_for_decision and status in {"stopped", "blocked_safety_review", "needs_revision"},
        "execute_apply_visible": False,
    }


def _verification_summary(item_results: list) -> dict:
    statuses: dict[str, int] = {}
    for item in item_results:
        verification = item.get("verification_result") if isinstance(item, dict) else {}
        status = str((verification or {}).get("status") or "not_recorded")
        statuses[status] = statuses.get(status, 0) + 1
    return {"statuses": statuses, "visible": bool(item_results)}


def _repair_summary(item_results: list, metadata: dict | None = None) -> list[dict]:
    repairs: list[dict] = []
    if isinstance(metadata, dict):
        for attempt in metadata.get("repair_attempts") or []:
            if isinstance(attempt, dict):
                repairs.append({"kind": "bounded_repair_plan", **attempt})
    for item in item_results:
        if not isinstance(item, dict):
            continue
        md = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for key in ("bounded_retry_result", "self_correction_result"):
            if md.get(key):
                repairs.append({"item_id": item.get("item_id", ""), "kind": key, "status": (md.get(key) or {}).get("status", "")})
    return repairs


def _unique(values: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
