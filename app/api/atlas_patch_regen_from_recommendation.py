from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_patch_regen_from_recommendation_policies import list_patch_regen_from_recommendation_policies
from agent.atlas_patch_regen_from_recommendation_schema import AtlasPatchRegenFromRecommendationRequest
from agent.atlas_patch_regen_from_recommendation_service import AtlasPatchRegenFromRecommendationService


router = APIRouter(prefix="/api/atlas/patch-regen-from-recommendation", tags=["atlas-patch-regen-from-recommendation"])


class LatestReq(BaseModel):
    pool_id: str


def _v(value: str, field: str, prefix: str = "") -> str:
    try:
        safe = validate_relative_path(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}:{exc}"})
    if prefix and not safe.startswith(prefix):
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}"})
    return safe


@router.get("/policies")
def policies():
    return {"policies": [p.model_dump() for p in list_patch_regen_from_recommendation_policies()]}


@router.post("/run")
def run(payload: AtlasPatchRegenFromRecommendationRequest):
    payload.pool_id = _v(payload.pool_id, "pool_id")
    payload.item_id = _v(payload.item_id, "item_id")
    payload.recommendation_run_id = _v(payload.recommendation_run_id, "recommendation_run_id", "regenrec_")
    if payload.run_id:
        payload.run_id = _v(payload.run_id, "run_id")
    return AtlasPatchRegenFromRecommendationService().run(payload).model_dump()


@router.get("/results/{pool_id}/{recommendation_exec_id}")
def result(pool_id: str, recommendation_exec_id: str):
    path = Path("ca_data") / "atlas" / "patch_regen_from_recommendations" / _v(pool_id, "pool_id") / f"{_v(recommendation_exec_id, 'recommendation_exec_id', 'regenexec_')}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/latest")
def latest(payload: LatestReq):
    root = Path("ca_data") / "atlas" / "patch_regen_from_recommendations" / _v(payload.pool_id, "pool_id")
    files = sorted(root.glob("regenexec_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files:
        raise HTTPException(status_code=404, detail={"error": "result_not_found", "reason": "result_not_found"})
    return json.loads(files[0].read_text(encoding="utf-8"))
