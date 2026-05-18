from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_llm_evaluator_policies import list_evaluator_policies
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService

router = APIRouter(prefix="/api/atlas/evaluator", tags=["atlas-evaluator"])
_svc = AtlasLLMEvaluatorService()


class AtlasEvaluatorLatestRequest(BaseModel):
    pool_id: str


def _validate_id(value: str, field: str, prefix: str = "") -> str:
    safe = validate_relative_path(value)
    if not safe or (prefix and not safe.startswith(prefix)):
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}"})
    return safe


@router.get("/policies")
def get_policies():
    return {"policies": [p.model_dump() for p in list_evaluator_policies()]}


@router.post("/evaluate")
def evaluate(payload: AtlasEvaluatorRequest):
    try:
        payload.pool_id = _validate_id(payload.pool_id, "pool_id")
        if payload.item_id:
            payload.item_id = _validate_id(payload.item_id, "item_id")
        if payload.run_id:
            payload.run_id = _validate_id(payload.run_id, "run_id")
        return _svc.evaluate(payload).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": str(exc)}) from exc


@router.get("/results/{pool_id}/{eval_id}")
def get_result(pool_id: str, eval_id: str):
    safe_pool = _validate_id(pool_id, "pool_id")
    safe_eval = _validate_id(eval_id, "eval_id", prefix="eval_")
    path = Path("ca_data") / "atlas" / "evaluator_results" / safe_pool / f"{safe_eval}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/latest")
def latest(payload: AtlasEvaluatorLatestRequest):
    safe_pool = _validate_id(payload.pool_id, "pool_id")
    root = Path("ca_data") / "atlas" / "evaluator_results" / safe_pool
    if not root.exists():
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    latest_file = sorted(root.glob("eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not latest_file:
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    return json.loads(latest_file[0].read_text(encoding="utf-8"))
