from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_auto_safe_apply_service import AtlasAutoSafeApplyService
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_context_refresh_service import AtlasContextRefreshService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_multi_item_autopilot_policies import list_multi_item_policies
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService
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


def _service() -> AtlasMultiItemAutopilotService:
    storage = AtlasPlanPoolStorage("ca_data")
    journal = AtlasJournal("ca_data")
    return AtlasMultiItemAutopilotService(
        storage=storage,
        journal=journal,
        automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AtlasAutoSafeApplyService(automation_gate=AtlasAutomationGateService(), safe_apply_service=AtlasSafeApplyExecutionService(storage=storage, journal=journal), journal=journal, storage=storage),
        auto_verification_service=AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=TestCommandRunner()),
        context_refresh_service=AtlasContextRefreshService(journal=journal),
        evaluator_service=AtlasLLMEvaluatorService(journal=journal),
    )


@router.get("/policies")
def get_policies():
    return {"policies": [p.model_dump() for p in list_multi_item_policies()]}


@router.post("/run")
def run(payload: AtlasMultiItemAutopilotRequest):
    payload.pool_id = _validate_id(payload.pool_id, "pool_id")
    if payload.run_id:
        payload.run_id = _validate_id(payload.run_id, "run_id")
    payload.item_ids = [_validate_id(v, "item_id") for v in (payload.item_ids or [])]
    return _service().run(payload).model_dump()


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
