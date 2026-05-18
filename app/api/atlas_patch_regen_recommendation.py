from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_patch_regen_recommendation_policies import list_patch_regen_recommendation_policies
from agent.atlas_patch_regen_recommendation_schema import AtlasPatchRegenRecommendationRequest
from agent.atlas_patch_regen_recommendation_service import AtlasPatchRegenRecommendationService

router = APIRouter(prefix="/api/atlas/patch-regen-recommendation", tags=["atlas-patch-regen-recommendation"])
class LatestReq(BaseModel):
    pool_id: str

def _v(v,f,pfx=""):
    try:s=validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
    if pfx and not s.startswith(pfx): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}"})
    return s

@router.get('/policies')
def policies(): return {"policies":[p.model_dump() for p in list_patch_regen_recommendation_policies()]}

@router.post('/run')
def run(payload:AtlasPatchRegenRecommendationRequest):
    payload.pool_id=_v(payload.pool_id,'pool_id'); payload.item_id=_v(payload.item_id,'item_id')
    payload.supervised_retry_run_id=_v(payload.supervised_retry_run_id,'supervised_retry_run_id','retryhandoff_')
    if payload.handoff_id: payload.handoff_id=_v(payload.handoff_id,'handoff_id','handoff_')
    if payload.safe_apply_execution_id: payload.safe_apply_execution_id=_v(payload.safe_apply_execution_id,'safe_apply_execution_id','safehandoff_')
    if payload.verification_run_id: payload.verification_run_id=_v(payload.verification_run_id,'verification_run_id','verifyhandoff_')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    return AtlasPatchRegenRecommendationService().recommend(payload).model_dump()

@router.get('/results/{pool_id}/{recommendation_run_id}')
def result(pool_id:str, recommendation_run_id:str):
    p=Path('ca_data')/'atlas'/'patch_regen_recommendations'/_v(pool_id,'pool_id')/f"{_v(recommendation_run_id,'recommendation_run_id','regenrec_')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))

@router.post('/latest')
def latest(payload:LatestReq):
    root=Path('ca_data')/'atlas'/'patch_regen_recommendations'/_v(payload.pool_id,'pool_id')
    files=sorted(root.glob('regenrec_*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
