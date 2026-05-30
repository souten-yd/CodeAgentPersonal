from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_auto_safe_apply_service import AtlasAutoSafeApplyService
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_context_refresh_service import AtlasContextRefreshService
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
from agent.atlas_self_correction_service import AtlasSelfCorrectionService
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService
from agent.atlas_workspace_root import resolve_atlas_workspace_root
from agent.test_command_runner import TestCommandRunner

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


def _build_safe_apply_execution_service(*, request, storage, journal, workspace_root) -> AtlasSafeApplyExecutionService:
    # Mirror the pipeline API wiring (app/api/atlas_pipeline.py:1158-1171): without an
    # implementation_executor + adapter, every item is blocked with
    # safe_apply_adapter_unavailable / safe_apply_executor_unavailable and nothing is ever applied.
    adapter_obj = getattr(getattr(request, "app", None), "state", None)
    adapter_obj = getattr(adapter_obj, "atlas_safe_apply_adapter", None) if adapter_obj is not None else None
    safe_apply_adapter = adapter_obj() if callable(adapter_obj) else adapter_obj
    if safe_apply_adapter is None:
        implementation_executor = getattr(getattr(request, "app", None), "state", None)
        implementation_executor = getattr(implementation_executor, "atlas_implementation_executor", None) if implementation_executor is not None else None
        if implementation_executor is None:
            implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=workspace_root)
        safe_apply_adapter = AtlasSafeApplyAdapter(implementation_executor=implementation_executor)
    # The app.state executor is pinned to Path.cwd() (main.py); rebind it to the pool workspace.
    impl = getattr(safe_apply_adapter, "implementation_executor", None)
    if impl is not None and hasattr(impl, "workspace_root"):
        try:
            safe_apply_adapter.implementation_executor = impl.__class__(workspace_root=workspace_root)
        except Exception:
            impl.workspace_root = workspace_root
    return AtlasSafeApplyExecutionService(storage=storage, journal=journal, safe_apply_adapter=safe_apply_adapter, workspace_root=workspace_root)


def _service(request: Request | None = None, workspace_id: str = "default", pool_id: str = "") -> AtlasMultiItemAutopilotService:
    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root)
    journal = AtlasJournal(root, workspace_id=workspace_id or "default")
    workspace_root = _resolve_pool_workspace_root(storage=storage, ca_data_root=root, workspace_id=workspace_id or "default", pool_id=pool_id)
    safe_apply_service = _build_safe_apply_execution_service(request=request, storage=storage, journal=journal, workspace_root=workspace_root)
    auto_safe_apply_service = AtlasAutoSafeApplyService(automation_gate=AtlasAutomationGateService(), safe_apply_service=safe_apply_service, journal=journal, storage=storage)
    auto_verification_service = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=TestCommandRunner())
    # Self-correction reuses the same apply/verify services and a patch generator backed by the app's
    # LLM json fn (None in tests -> the service is simply not constructed and the loop is a no-op).
    llm_json_fn = getattr(getattr(getattr(request, "app", None), "state", None), "atlas_llm_json_fn", None)
    self_correction_service = None
    if llm_json_fn is not None:
        patch_proposal_service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm_json_fn)
        self_correction_service = AtlasSelfCorrectionService(
            storage=storage,
            journal=journal,
            patch_proposal_service=patch_proposal_service,
            auto_safe_apply_service=auto_safe_apply_service,
            auto_verification_service=auto_verification_service,
        )
    return AtlasMultiItemAutopilotService(
        storage=storage,
        journal=journal,
        automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=auto_safe_apply_service,
        auto_verification_service=auto_verification_service,
        context_refresh_service=AtlasContextRefreshService(journal=journal),
        evaluator_service=AtlasLLMEvaluatorService(journal=journal),
        bounded_retry_service=AtlasBoundedRetryService(storage=storage, journal=journal, auto_verification_service=AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=TestCommandRunner()), context_refresh_service=AtlasContextRefreshService(journal=journal), evaluator_service=AtlasLLMEvaluatorService(journal=journal)),
        self_correction_service=self_correction_service,
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
    return _service(request, payload.workspace_id, pool_id=payload.pool_id).run(payload).model_dump()


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
