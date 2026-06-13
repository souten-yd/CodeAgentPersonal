from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_codegen_progress import read_progress, write_progress
from agent.atlas_auto_safe_apply_service import AtlasAutoSafeApplyService
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_multi_item_autopilot_policies import list_multi_item_policies
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_correction_router_service import AtlasCorrectionRouterService
from agent.atlas_failure_diagnosis_service import AtlasFailureDiagnosisService
from agent.atlas_test_harness_provisioner import AtlasTestHarnessProvisioner
from agent.atlas_workspace_root import resolve_atlas_workspace_root
from agent.project_intelligence.adapters.atlas_context_refresh import AtlasContextRefreshAdapter
from agent.test_command_runner import TestCommandRunner
from app.api.atlas_autopilot_factory import build_safe_apply_execution_service, build_self_correction_service, _project_intelligence_coordinator

router = APIRouter(prefix="/api/atlas/multi-item-autopilot", tags=["atlas-multi-item-autopilot"])


class AtlasMultiItemLatestRequest(BaseModel):
    pool_id: str


def _validate_id(value: str, field: str, prefix: str = "") -> str:
    try:
        safe = validate_relative_path(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}:{exc}"}) from exc
    if not safe or (prefix and not safe.startswith(prefix)):
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}"})
    return safe


def _resolve_pool_workspace_root(*, storage: AtlasPlanPoolStorage, ca_data_root, workspace_id: str, pool_id: str):
    project_path = ""
    try:
        pool = storage.load_pool(pool_id)
        project_path = str(getattr(pool, "project_path", "") or "")
    except Exception:
        project_path = ""
    return resolve_atlas_workspace_root(ca_data_root=ca_data_root, workspace_id=workspace_id, project_path=project_path)


def _service(request: Request | None = None, workspace_id: str = "default", pool_id: str = "") -> AtlasMultiItemAutopilotService:
    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root)
    journal = AtlasJournal(root, workspace_id=workspace_id or "default")
    workspace_root = _resolve_pool_workspace_root(storage=storage, ca_data_root=root, workspace_id=workspace_id or "default", pool_id=pool_id)
    safe_apply_service = build_safe_apply_execution_service(request=request, storage=storage, journal=journal, workspace_root=workspace_root)
    auto_safe_apply_service = AtlasAutoSafeApplyService(automation_gate=AtlasAutomationGateService(), safe_apply_service=safe_apply_service, journal=journal, storage=storage)
    auto_verification_service = AtlasAutoVerificationService(
        journal=journal,
        storage=storage,
        command_runner=TestCommandRunner(),
        project_intelligence=_project_intelligence_coordinator(request),
    )
    # Self-correction reuses the same apply/verify services and a patch generator backed by the app's
    # LLM json fn (None in tests -> the service is simply not constructed and the loop is a no-op).
    llm_json_fn = getattr(getattr(getattr(request, "app", None), "state", None), "atlas_llm_json_fn", None)
    self_correction_service = build_self_correction_service(
        request=request,
        storage=storage,
        journal=journal,
        workspace_root=workspace_root,
        command_runner=TestCommandRunner(),
    )
    correction_router_service = None
    if llm_json_fn is not None and self_correction_service is not None:
        patch_proposal_service = AtlasPatchProposalService(
            journal=journal,
            storage=storage,
            llm_json_fn=llm_json_fn,
            project_intelligence=_project_intelligence_coordinator(request),
        )
        # Routes a test failure caused by a code bug back to regenerating the implementation item.
        correction_router_service = AtlasCorrectionRouterService(
            storage=storage,
            journal=journal,
            patch_proposal_service=patch_proposal_service,
            auto_safe_apply_service=auto_safe_apply_service,
            auto_verification_service=auto_verification_service,
            self_correction_service=self_correction_service,
            diagnosis_service=AtlasFailureDiagnosisService(llm_json_fn=llm_json_fn),
        )
    context_refresh = AtlasContextRefreshAdapter(data_root=root).build_service(journal=journal)
    return AtlasMultiItemAutopilotService(
        storage=storage,
        journal=journal,
        automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=auto_safe_apply_service,
        auto_verification_service=auto_verification_service,
        context_refresh_service=context_refresh,
        evaluator_service=AtlasLLMEvaluatorService(journal=journal),
        bounded_retry_service=AtlasBoundedRetryService(
            storage=storage,
            journal=journal,
            auto_verification_service=AtlasAutoVerificationService(
                journal=journal,
                storage=storage,
                command_runner=TestCommandRunner(),
                project_intelligence=_project_intelligence_coordinator(request),
            ),
            context_refresh_service=context_refresh,
            evaluator_service=AtlasLLMEvaluatorService(journal=journal),
        ),
        self_correction_service=self_correction_service,
        harness_provisioner=AtlasTestHarnessProvisioner(),
        correction_router_service=correction_router_service,
    )


@router.get("/policies")
def get_policies():
    return {"policies": [p.model_dump() for p in list_multi_item_policies()]}


@router.post("/run")
def run(payload: AtlasMultiItemAutopilotRequest, request: Request):
    payload.pool_id = _validate_id(payload.pool_id, "pool_id")
    if payload.run_id:
        payload.run_id = _validate_id(payload.run_id, "run_id")
    payload.item_ids = [_validate_id(v, "item_id") for v in (payload.item_ids or [])]
    # Validate the pool exists up front so a missing/unreadable pool returns a clean 404 instead of a
    # bare 500 from deep inside the service.
    root = resolve_atlas_ca_data_root(request)
    try:
        AtlasPlanPoolStorage(root).load_pool(payload.pool_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"error": "pool_not_found", "reason": f"pool_not_found:{payload.pool_id}"}) from exc
    # Inject the data root + a progress key so the service writes live sub-phase progress
    # (context_refresh / safe_apply / verification / self_correction) that the UI can poll, instead of
    # looking "stuck at apply" during the long synchronous apply+verify+repair.
    progress_run_id = payload.run_id or f"autopilot_{uuid4().hex[:10]}"
    payload.run_id = progress_run_id
    meta = dict(payload.metadata or {})
    meta.setdefault("data_root", str(root))
    meta["orchestrator_run_id"] = progress_run_id
    payload.metadata = meta
    write_progress(root, payload.pool_id, progress_run_id, {
        "run_id": progress_run_id, "orchestrator_run_id": progress_run_id,
        "phase": "candidate_apply", "sub_phase": "starting", "status": "running", "last_event": "autopilot_started",
    })
    # Build + run inside a guard: surface service/executor wiring failures as a structured 500 rather
    # than leaking an unhandled exception (the "Apply: Internal Server Error" the user saw).
    try:
        return _service(request, payload.workspace_id, pool_id=payload.pool_id).run(payload).model_dump()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": "autopilot_failed", "reason": f"{exc.__class__.__name__}: {exc}"[:300]},
        ) from exc


@router.get("/progress")
def get_progress(request: Request, pool_id: str = Query(...), run_id: str = Query(...)) -> dict:
    """Live sub-phase progress of a synchronous autopilot run, so the UI can show what is executing
    now (applying / browser-smoke verifying / auto-repairing) instead of a static "apply"."""
    pool_id = _validate_id(pool_id, "pool_id")
    progress = read_progress(resolve_atlas_ca_data_root(request), pool_id, run_id)
    if not progress:
        return {"pool_id": pool_id, "run_id": run_id, "found": False}
    return {
        "pool_id": pool_id,
        "run_id": run_id,
        "found": True,
        "phase": progress.get("phase", ""),
        "sub_phase": progress.get("sub_phase", ""),
        "last_event": progress.get("last_event", ""),
        "attempt": int(progress.get("attempt") or 0),
        "current_item_index": int(progress.get("current_item_index") or 0),
        "total_items": int(progress.get("total_items") or 0),
        "status": progress.get("status", ""),
        "heartbeat_at": progress.get("heartbeat_at", ""),
    }


@router.get("/results/{pool_id}/{autopilot_run_id}")
def get_result(pool_id: str, autopilot_run_id: str):
    safe_pool = _validate_id(pool_id, "pool_id")
    safe_id = _validate_id(autopilot_run_id, "autopilot_run_id", prefix="auto_")
    path = Path("ca_data") / "atlas" / "multi_item_autopilot" / safe_pool / f"{safe_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/latest")
def latest(payload: AtlasMultiItemLatestRequest):
    safe_pool = _validate_id(payload.pool_id, "pool_id")
    root = Path("ca_data") / "atlas" / "multi_item_autopilot" / safe_pool
    files = sorted(root.glob("auto_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files:
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    return json.loads(files[0].read_text(encoding="utf-8"))
