from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_manual_next_action_executor_policies import list_manual_next_action_executor_policies
from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorRequest
from agent.atlas_manual_next_action_executor_service import AtlasManualNextActionExecutorService
from agent.atlas_patch_candidate_approval_service import AtlasPatchCandidateApprovalService
from agent.atlas_patch_regen_from_recommendation_service import AtlasPatchRegenFromRecommendationService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_retry_service import AtlasSupervisedHandoffRetryService
from agent.atlas_supervised_handoff_safe_apply_service import AtlasSupervisedHandoffSafeApplyService
from agent.atlas_supervised_handoff_verification_service import AtlasSupervisedHandoffVerificationService

router = APIRouter(prefix='/api/atlas/manual-next-action-executor', tags=['atlas-manual-next-action-executor'])
class LatestReq(BaseModel): pool_id:str
class TokenReq(BaseModel): orchestrator_run_id:str; action_id:str; expected_next_action:str; item_id:str

def _v(v,f):
    try:return validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
def _svc():
    st=AtlasPlanPoolStorage('ca_data');jr=AtlasJournal('ca_data')
    return AtlasManualNextActionExecutorService(storage=st,journal=jr,approval_service=AtlasPatchCandidateApprovalService(storage=st,journal=jr),safe_apply_service=AtlasSupervisedHandoffSafeApplyService(storage=st,journal=jr),verification_service=AtlasSupervisedHandoffVerificationService(storage=st,journal=jr),retry_service=AtlasSupervisedHandoffRetryService(storage=st,journal=jr),patch_regen_service=AtlasPatchRegenFromRecommendationService(storage=st,journal=jr))

@router.get('/policies')
def policies(): return {'policies':[p.model_dump() for p in list_manual_next_action_executor_policies()]}
@router.post('/execute')
def execute(payload:AtlasManualNextActionExecutorRequest):
    payload.pool_id=_v(payload.pool_id,'pool_id')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    if not payload.orchestrator_run_id.startswith('nextaction_'): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_orchestrator_run_id"})
    return _svc().execute(payload).model_dump()
@router.get('/results/{pool_id}/{executor_run_id}')
def result(pool_id:str, executor_run_id:str):
    if not executor_run_id.startswith('manualexec_'): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_executor_run_id"})
    p=Path('ca_data')/'atlas'/'manual_next_action_executor'/_v(pool_id,'pool_id')/f"{_v(executor_run_id,'executor_run_id')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))
@router.post('/latest')
def latest(payload:LatestReq):
    root=Path('ca_data')/'atlas'/'manual_next_action_executor'/_v(payload.pool_id,'pool_id')
    files=sorted(root.glob('manualexec_*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
@router.post('/confirmation-token-preview')
def token_preview(payload:TokenReq):
    if not payload.orchestrator_run_id.startswith('nextaction_'): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_orchestrator_run_id"})
    return {"confirmation_token":f"MANUAL_EXECUTE:{payload.orchestrator_run_id}:{payload.action_id}:{payload.expected_next_action}:{payload.item_id}","confirmation_text":"EXECUTE ONE ACTION"}
