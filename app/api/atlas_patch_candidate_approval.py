from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_patch_candidate_approval_policies import list_patch_candidate_approval_policies
from agent.atlas_patch_candidate_approval_schema import AtlasPatchCandidateApprovalRequest
from agent.atlas_patch_candidate_approval_service import AtlasPatchCandidateApprovalService

router = APIRouter(prefix="/api/atlas/patch-candidate-approval", tags=["atlas-patch-candidate-approval"])

class LatestReq(BaseModel):
    pool_id: str


def _v(v: str, f: str, pfx: str = "") -> str:
    try: s = validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
    if pfx and not s.startswith(pfx): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}"})
    return s

@router.get('/policies')
def policies(): return {"policies":[p.model_dump() for p in list_patch_candidate_approval_policies()]}

@router.post('/decide')
def decide(payload: AtlasPatchCandidateApprovalRequest):
    payload.pool_id=_v(payload.pool_id,'pool_id'); payload.item_id=_v(payload.item_id,'item_id'); payload.regen_run_id=_v(payload.regen_run_id,'regen_run_id','regen_')
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    if payload.proposal_id: payload.proposal_id=_v(payload.proposal_id,'proposal_id')
    return AtlasPatchCandidateApprovalService().decide(payload).model_dump()

@router.get('/results/{pool_id}/{approval_run_id}')
def result(pool_id:str, approval_run_id:str):
    p=Path('ca_data')/'atlas'/'patch_candidate_approvals'/_v(pool_id,'pool_id')/f"{_v(approval_run_id,'approval_run_id','approval_')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))

@router.post('/latest')
def latest(payload:LatestReq):
    root=Path('ca_data')/'atlas'/'patch_candidate_approvals'/_v(payload.pool_id,'pool_id')
    files=sorted(root.glob('approval_*.json'),key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))

handoff_router = APIRouter(prefix='/api/atlas/safe-apply-handoffs', tags=['atlas-safe-apply-handoffs'])

@handoff_router.get('/{pool_id}/{handoff_id}')
def get_handoff(pool_id:str, handoff_id:str):
    p=Path('ca_data')/'atlas'/'safe_apply_handoffs'/_v(pool_id,'pool_id')/f"{_v(handoff_id,'handoff_id','handoff_')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))

@handoff_router.post('/latest')
def latest_handoff(payload:LatestReq):
    root=Path('ca_data')/'atlas'/'safe_apply_handoffs'/_v(payload.pool_id,'pool_id')
    files=sorted(root.glob('handoff_*.json'),key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
