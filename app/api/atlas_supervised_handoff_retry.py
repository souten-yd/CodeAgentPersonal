from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.project_intelligence.adapters.atlas_context_refresh import AtlasContextRefreshAdapter
from agent.atlas_supervised_handoff_retry_policies import list_supervised_handoff_retry_policies
from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryRequest
from agent.atlas_supervised_handoff_retry_service import AtlasSupervisedHandoffRetryService
from agent.test_command_runner import TestCommandRunner

router = APIRouter(prefix="/api/atlas/supervised-handoff-retry", tags=["atlas-supervised-handoff-retry"])
class LatestReq(BaseModel):
    pool_id: str

def _v(v,f,pfx=""):
    try:s=validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
    if pfx and not s.startswith(pfx): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}"})
    return s

def _svc(request: Request | None = None, workspace_id: str = "default"):
    root = resolve_atlas_ca_data_root(request)
    storage=AtlasPlanPoolStorage(root); journal=AtlasJournal(root, workspace_id=workspace_id or "default")
    context_refresh = AtlasContextRefreshAdapter(data_root=root).build_service(journal=journal)
    br=AtlasBoundedRetryService(storage=storage,journal=journal,auto_verification_service=AtlasAutoVerificationService(journal=journal,storage=storage,command_runner=TestCommandRunner()),context_refresh_service=context_refresh,evaluator_service=AtlasLLMEvaluatorService(journal=journal))
    return AtlasSupervisedHandoffRetryService(storage=storage,journal=journal,bounded_retry_service=br)

@router.get('/policies')
def policies(): return {"policies":[p.model_dump() for p in list_supervised_handoff_retry_policies()]}
@router.post('/run')
def run(payload:AtlasSupervisedHandoffRetryRequest, request: Request):
    payload.pool_id=_v(payload.pool_id,'pool_id'); payload.item_id=_v(payload.item_id,'item_id')
    payload.safe_apply_execution_id=_v(payload.safe_apply_execution_id,'safe_apply_execution_id','safehandoff_')
    payload.verification_run_id=_v(payload.verification_run_id,'verification_run_id','verifyhandoff_')
    if payload.handoff_id: payload.handoff_id=_v(payload.handoff_id,'handoff_id','handoff_')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    return _svc(request, payload.workspace_id).run(payload).model_dump()
@router.get('/results/{pool_id}/{supervised_retry_run_id}')
def result(pool_id:str, supervised_retry_run_id:str):
    p=Path('ca_data')/'atlas'/'supervised_handoff_retry'/_v(pool_id,'pool_id')/f"{_v(supervised_retry_run_id,'supervised_retry_run_id','retryhandoff_')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))
@router.post('/latest')
def latest(payload:LatestReq):
    root=Path('ca_data')/'atlas'/'supervised_handoff_retry'/_v(payload.pool_id,'pool_id')
    files=sorted(root.glob('retryhandoff_*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
