from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_supervised_handoff_safe_apply_policies import list_supervised_handoff_safe_apply_policies
from agent.atlas_supervised_handoff_safe_apply_schema import AtlasSupervisedHandoffSafeApplyRequest
from agent.atlas_supervised_handoff_safe_apply_service import AtlasSupervisedHandoffSafeApplyService

router = APIRouter(prefix="/api/atlas/supervised-handoff-safe-apply", tags=["atlas-supervised-handoff-safe-apply"])
class LatestReq(BaseModel): pool_id:str

def _v(v:str,f:str,pfx:str=""):
    try: s=validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400,detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
    if pfx and not s.startswith(pfx): raise HTTPException(status_code=400,detail={"error":"invalid_request","reason":f"invalid_{f}"})
    return s

@router.get('/policies')
def policies(): return {"policies":[p.model_dump() for p in list_supervised_handoff_safe_apply_policies()]}

@router.post('/execute')
def execute(payload:AtlasSupervisedHandoffSafeApplyRequest):
    payload.pool_id=_v(payload.pool_id,'pool_id'); payload.item_id=_v(payload.item_id,'item_id'); payload.handoff_id=_v(payload.handoff_id,'handoff_id','handoff_')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    return AtlasSupervisedHandoffSafeApplyService().execute(payload).model_dump()

@router.get('/results/{pool_id}/{execution_id}')
def result(pool_id:str, execution_id:str):
    p=Path('ca_data')/'atlas'/'supervised_handoff_safe_apply'/_v(pool_id,'pool_id')/f"{_v(execution_id,'execution_id','safehandoff_')}.json"
    if not p.exists(): raise HTTPException(status_code=404,detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))

@router.post('/latest')
def latest(payload:LatestReq):
    root=Path('ca_data')/'atlas'/'supervised_handoff_safe_apply'/_v(payload.pool_id,'pool_id')
    files=sorted(root.glob('safehandoff_*.json'),key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404,detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
