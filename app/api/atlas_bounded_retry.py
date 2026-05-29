from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_bounded_retry_policies import list_bounded_retry_policies
from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_context_refresh_service import AtlasContextRefreshService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.test_command_runner import TestCommandRunner

router = APIRouter(prefix="/api/atlas/bounded-retry", tags=["atlas-bounded-retry"])

class LatestReq(BaseModel):
    pool_id: str

def _validate(v: str, field: str, prefix: str = "") -> str:
    try: safe = validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{field}:{exc}"})
    if not safe or (prefix and not safe.startswith(prefix)):
        raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{field}"})
    return safe

def _svc(request: Request | None = None, workspace_id: str = "default") -> AtlasBoundedRetryService:
    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root); journal = AtlasJournal(root, workspace_id=workspace_id or "default")
    return AtlasBoundedRetryService(storage=storage, journal=journal, auto_verification_service=AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=TestCommandRunner()), context_refresh_service=AtlasContextRefreshService(journal=journal), evaluator_service=AtlasLLMEvaluatorService(journal=journal))

@router.get('/policies')
def policies():
    return {"policies": [p.model_dump() for p in list_bounded_retry_policies()]}

@router.post('/run')
def run(payload: AtlasBoundedRetryRequest, request: Request):
    payload.pool_id = _validate(payload.pool_id, 'pool_id'); payload.item_id = _validate(payload.item_id,'item_id')
    if payload.run_id: payload.run_id = _validate(payload.run_id,'run_id')
    return _svc(request, payload.workspace_id).run(payload).model_dump()

@router.get('/results/{pool_id}/{retry_run_id}')
def result(pool_id: str, retry_run_id: str):
    p = Path('ca_data') / 'atlas' / 'bounded_retry' / _validate(pool_id,'pool_id') / f"{_validate(retry_run_id,'retry_run_id','retry_')}.json"
    if not p.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(p.read_text(encoding='utf-8'))

@router.post('/latest')
def latest(payload: LatestReq):
    root = Path('ca_data') / 'atlas' / 'bounded_retry' / _validate(payload.pool_id,'pool_id')
    files = sorted(root.glob('retry_*.json'), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
