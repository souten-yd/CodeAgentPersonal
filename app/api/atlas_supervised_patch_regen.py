from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_supervised_patch_regen_policies import list_patch_regen_policies
from agent.atlas_supervised_patch_regen_schema import AtlasPatchRegenRequest
from agent.atlas_supervised_patch_regen_service import AtlasSupervisedPatchRegenService

router = APIRouter(prefix="/api/atlas/patch-regen", tags=["atlas-patch-regen"])

class LatestReq(BaseModel):
    pool_id: str

def _validate(v: str, field: str, prefix: str = "") -> str:
    try: safe = validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{field}:{exc}"})
    if prefix and not safe.startswith(prefix):
        raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{field}"})
    return safe

@router.get('/policies')
def policies():
    return {"policies": [p.model_dump() for p in list_patch_regen_policies()]}

@router.post('/run')
def run(payload: AtlasPatchRegenRequest):
    payload.pool_id = _validate(payload.pool_id, 'pool_id'); payload.item_id = _validate(payload.item_id, 'item_id')
    if payload.run_id: payload.run_id = _validate(payload.run_id, 'run_id')
    if payload.context_bundle_id: payload.context_bundle_id = _validate(payload.context_bundle_id, 'context_bundle_id', 'ctx_')
    if payload.retry_run_id: payload.retry_run_id = _validate(payload.retry_run_id, 'retry_run_id', 'retry_')
    if payload.evaluator_result_id: payload.evaluator_result_id = _validate(payload.evaluator_result_id, 'evaluator_result_id', 'eval_')
    if payload.regen_run_id: payload.regen_run_id = _validate(payload.regen_run_id, 'regen_run_id', 'regen_')
    payload.target_files = [_validate(p, 'target_file') for p in payload.target_files]
    return AtlasSupervisedPatchRegenService().regenerate(payload).model_dump()

@router.get('/results/{pool_id}/{regen_run_id}')
def result(pool_id: str, regen_run_id: str):
    p = Path('ca_data') / 'atlas' / 'patch_regen' / _validate(pool_id, 'pool_id') / f"{_validate(regen_run_id,'regen_run_id','regen_')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))

@router.post('/latest')
def latest(payload: LatestReq):
    root = Path('ca_data') / 'atlas' / 'patch_regen' / _validate(payload.pool_id,'pool_id')
    files = sorted(root.glob('regen_*.json'), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
