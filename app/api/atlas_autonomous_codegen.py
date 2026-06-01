from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.api.atlas_multi_item_autopilot import _service as _build_multi_item_service, _validate_id
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
    try:
        AtlasPlanPoolStorage(root).load_pool(payload.pool_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"error": "pool_not_found", "reason": f"pool_not_found:{payload.pool_id}"}) from exc
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
    return {
        "pool_id": payload.get("pool_id", ""),
        "run_id": payload.get("run_id", ""),
        "orchestrator_run_id": payload.get("orchestrator_run_id", ""),
        "status": payload.get("status", ""),
        "current_phase": payload.get("phase", ""),
        "next_action": _next_action(payload),
        "summary": payload,
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
    if status in {"stopped", "blocked_safety_review"}:
        return f"Resolve stop reason: {payload.get('stop_reason') or 'blocked'}"
    if phase == "needs_scope_confirmation":
        return "Answer clarification, revise plan, and rerun gates."
    if phase == "waiting_for_critical_decision":
        return "Review critical event and choose an explicit user decision."
    if status in {"completed", "partial"}:
        return "Review final summary and prepare draft PR artifact when allowed."
    return "Poll status or inspect the autonomous code-generation result."
