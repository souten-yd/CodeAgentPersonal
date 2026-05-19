from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_guarded_operator_loop_policies import list_guarded_operator_loop_policies
from agent.atlas_guarded_operator_loop_schema import ALLOWED_GUARDED_LOOP_ACTIONS, ALLOWED_GUARDED_LOOP_EXPLICIT_DECISIONS, ALLOWED_GUARDED_LOOP_MODES, AtlasGuardedOperatorLoopRequest
from agent.atlas_guarded_operator_loop_service import AtlasGuardedOperatorLoopService
from agent.atlas_journal import AtlasJournal
from agent.atlas_manual_next_action_executor_service import AtlasManualNextActionExecutorService
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_next_action_orchestrator_service import AtlasNextActionOrchestratorService
from agent.atlas_patch_candidate_approval_service import AtlasPatchCandidateApprovalService
from agent.atlas_patch_regen_from_recommendation_service import AtlasPatchRegenFromRecommendationService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_post_manual_execution_refresh_service import AtlasPostManualExecutionRefreshService
from agent.atlas_supervised_handoff_retry_service import AtlasSupervisedHandoffRetryService
from agent.atlas_supervised_handoff_safe_apply_service import AtlasSupervisedHandoffSafeApplyService
from agent.atlas_supervised_handoff_verification_service import AtlasSupervisedHandoffVerificationService
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService
from app.api.atlas_root import resolve_atlas_ca_data_root

router=APIRouter(prefix='/api/atlas/guarded-operator-loop',tags=['atlas-guarded-operator-loop'])
class LatestReq(BaseModel): pool_id:str

def bad(reason): raise HTTPException(status_code=400,detail={"error":"invalid_request","reason":reason})
def v(x,n):
    try:return validate_relative_path(x)
    except Exception as exc: bad(f'invalid_{n}:{exc}')

def svc(request: Request):
    root=resolve_atlas_ca_data_root(request); st=AtlasPlanPoolStorage(root); jr=AtlasJournal(root); sis=AtlasSupervisedItemStatusService(storage=st,journal=jr); ms=AtlasMultiItemSupervisedStatusService(storage=st,journal=jr,supervised_item_status_service=sis); no=AtlasNextActionOrchestratorService(storage=st,journal=jr,supervised_status_service=ms)
    me=AtlasManualNextActionExecutorService(storage=st,journal=jr,approval_service=AtlasPatchCandidateApprovalService(storage=st,journal=jr),safe_apply_service=AtlasSupervisedHandoffSafeApplyService(storage=st,journal=jr),verification_service=AtlasSupervisedHandoffVerificationService(storage=st,journal=jr),retry_service=AtlasSupervisedHandoffRetryService(storage=st,journal=jr),patch_regen_service=AtlasPatchRegenFromRecommendationService(storage=st,journal=jr),data_root=root)
    pr=AtlasPostManualExecutionRefreshService(storage=st,journal=jr,supervised_item_status_service=sis,multi_status_service=ms,next_action_orchestrator_service=no,data_root=root)
    return AtlasGuardedOperatorLoopService(journal=jr,multi_status_service=ms,next_action_orchestrator_service=no,manual_executor_service=me,post_refresh_service=pr,data_root=root)

@router.get('/policies')
def policies(): return {'policies':[p.model_dump() for p in list_guarded_operator_loop_policies()]}
@router.post('/run')
def run(payload:AtlasGuardedOperatorLoopRequest, request: Request):
    payload.pool_id=v(payload.pool_id,'pool_id'); payload.run_id= v(payload.run_id,'run_id') if payload.run_id else ''
    if payload.mode not in ALLOWED_GUARDED_LOOP_MODES: bad('invalid_mode')
    if payload.expected_next_action and payload.expected_next_action not in ALLOWED_GUARDED_LOOP_ACTIONS: bad('invalid_expected_next_action')
    if payload.explicit_decision not in ALLOWED_GUARDED_LOOP_EXPLICIT_DECISIONS: bad('invalid_explicit_decision')
    for key,prefix in [('multi_status_run_id','multistatus_'),('orchestrator_run_id','nextaction_'),('executor_run_id','manualexec_')]:
        val=getattr(payload,key)
        if val:
            v(val,key)
            if not val.startswith(prefix): bad(f'invalid_{key}')
    if payload.action_id: payload.action_id=v(payload.action_id,'action_id')
    return svc(request).run(payload).model_dump()
@router.get('/results/{pool_id}/{loop_run_id}')
def result(pool_id:str, loop_run_id:str, request: Request):
    if not loop_run_id.startswith('guardloop_'): bad('invalid_loop_run_id')
    p=resolve_atlas_ca_data_root(request)/'atlas'/'guarded_operator_loop'/v(pool_id,'pool_id')/f"{v(loop_run_id,'loop_run_id')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))
@router.post('/latest')
def latest(payload:LatestReq, request: Request):
    root=resolve_atlas_ca_data_root(request)/'atlas'/'guarded_operator_loop'/v(payload.pool_id,'pool_id'); files=sorted(root.glob('guardloop_*.json'),key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
