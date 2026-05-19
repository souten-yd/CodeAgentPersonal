from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_next_action_orchestrator_service import AtlasNextActionOrchestratorService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_post_manual_execution_refresh_policies import list_post_manual_execution_refresh_policies
from agent.atlas_post_manual_execution_refresh_schema import AtlasPostManualExecutionRefreshRequest
from agent.atlas_post_manual_execution_refresh_service import AtlasPostManualExecutionRefreshService
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService

router=APIRouter(prefix='/api/atlas/post-manual-execution-refresh',tags=['atlas-post-manual-execution-refresh'])
class LatestReq(BaseModel): pool_id:str; run_id:str=''; executor_run_id:str=''
def _v(v,f):
    try:return validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
def _bad(r): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":r})
def _svc():
    st=AtlasPlanPoolStorage('ca_data'); jr=AtlasJournal('ca_data'); sis=AtlasSupervisedItemStatusService(storage=st,journal=jr); ms=AtlasMultiItemSupervisedStatusService(storage=st,journal=jr,supervised_item_status_service=sis); na=AtlasNextActionOrchestratorService(storage=st,journal=jr,supervised_status_service=ms)
    return AtlasPostManualExecutionRefreshService(storage=st,journal=jr,supervised_item_status_service=sis,multi_status_service=ms,next_action_orchestrator_service=na)
@router.get('/policies')
def policies(): return {'policies':[p.model_dump() for p in list_post_manual_execution_refresh_policies()]}
@router.post('/refresh')
def refresh(payload:AtlasPostManualExecutionRefreshRequest):
    payload.pool_id=_v(payload.pool_id,'pool_id')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    payload.executor_run_id=_v(payload.executor_run_id,'executor_run_id')
    if not payload.executor_run_id.startswith('manualexec_'): _bad('invalid_executor_run_id')
    return _svc().refresh(payload).model_dump()
@router.get('/results/{pool_id}/{refresh_run_id}')
def result(pool_id:str, refresh_run_id:str):
    pid=_v(pool_id,'pool_id'); rr=_v(refresh_run_id,'refresh_run_id')
    if not rr.startswith('postexec_'): _bad('invalid_refresh_run_id')
    p=Path('ca_data')/'atlas'/'post_manual_execution_refresh'/pid/f'{rr}.json'
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"invalid_request","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))
@router.post('/latest')
def latest(payload:LatestReq):
    pid=_v(payload.pool_id,'pool_id'); root=Path('ca_data')/'atlas'/'post_manual_execution_refresh'/pid
    files=sorted(root.glob('postexec_*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"invalid_request","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
