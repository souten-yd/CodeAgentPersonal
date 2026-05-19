from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_next_action_orchestrator_policies import list_next_action_orchestrator_policies
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorRequest
from agent.atlas_next_action_orchestrator_service import AtlasNextActionOrchestratorService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/atlas/next-action-orchestrator", tags=["atlas-next-action-orchestrator"])
ALLOWED_ACTIONS={"approve_patch_candidate","run_supervised_safe_apply","run_supervised_verification","run_supervised_retry","run_patch_regen_from_recommendation","manual_review","investigate_failure","none",""}
class LatestReq(BaseModel): pool_id:str; run_id:str=""; item_id:str=""; requested_next_action:str=""
def _v(v,f):
    try:return validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
def _svc(request: Request):
    root = resolve_atlas_ca_data_root(request)
    st=AtlasPlanPoolStorage(root);jr=AtlasJournal(root); sis=AtlasSupervisedItemStatusService(storage=st,journal=jr); ms=AtlasMultiItemSupervisedStatusService(storage=st,journal=jr,supervised_item_status_service=sis,data_root=root)
    return AtlasNextActionOrchestratorService(storage=st,journal=jr,supervised_status_service=ms,data_root=root)
@router.get('/policies')
def policies(): return {"policies":[p.model_dump() for p in list_next_action_orchestrator_policies()]}
@router.post('/prepare')
def prepare(payload: AtlasNextActionOrchestratorRequest, request: Request):
    payload.pool_id=_v(payload.pool_id,'pool_id')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    if payload.item_id: payload.item_id=_v(payload.item_id,'item_id')
    if payload.multi_status_run_id and not payload.multi_status_run_id.startswith('multistatus_'): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_multi_status_run_id"})
    if payload.requested_next_action not in ALLOWED_ACTIONS: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_requested_next_action"})
    try:
        return _svc(request).prepare(payload).model_dump()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"pool_not_found"})
@router.get('/results/{pool_id}/{orchestrator_run_id}')
def result(pool_id:str, orchestrator_run_id:str, request: Request):
    pid=_v(pool_id,'pool_id')
    if not orchestrator_run_id.startswith('nextaction_'): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_orchestrator_run_id"})
    root = resolve_atlas_ca_data_root(request)
    path=root/'atlas'/'next_action_orchestrator'/pid/f"{_v(orchestrator_run_id,'orchestrator_run_id')}.json"
    if not path.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(path.read_text(encoding='utf-8'))
@router.post('/latest')
def latest(payload: LatestReq, request: Request):
    pid=_v(payload.pool_id,'pool_id'); root=resolve_atlas_ca_data_root(request)/'atlas'/'next_action_orchestrator'/pid
    files=sorted(root.glob('nextaction_*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
