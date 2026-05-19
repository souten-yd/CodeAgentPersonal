from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_supervised_status_policies import list_multi_item_supervised_status_policies
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService
router = APIRouter(prefix="/api/atlas/multi-item-supervised-status", tags=["atlas-multi-item-supervised-status"])
class LatestReq(BaseModel): pool_id: str
def _v(v,f):
    try: return validate_relative_path(v)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{f}:{exc}"})
@router.get('/policies')
def policies(): return {"policies":[p.model_dump() for p in list_multi_item_supervised_status_policies()]}
def _svc():
    st=AtlasPlanPoolStorage('ca_data'); jr=AtlasJournal('ca_data'); sis=AtlasSupervisedItemStatusService(storage=st,journal=jr)
    return AtlasMultiItemSupervisedStatusService(storage=st,journal=jr,supervised_item_status_service=sis)
@router.post('/build')
def build(payload: AtlasMultiItemSupervisedStatusRequest):
    payload.pool_id=_v(payload.pool_id,'pool_id');
    if payload.run_id: payload.run_id=_v(payload.run_id,'run_id')
    payload.item_ids=[_v(i,'item_id') for i in (payload.item_ids or [])]
    return _svc().build_status(payload).model_dump()
@router.get('/results/{pool_id}/{multi_status_run_id}')
def result(pool_id: str, multi_status_run_id: str):
    pid=_v(pool_id,'pool_id')
    if not multi_status_run_id.startswith('multistatus_'): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_multi_status_run_id"})
    path=Path('ca_data')/'atlas'/'multi_item_supervised_status'/pid/f"{_v(multi_status_run_id,'multi_status_run_id')}.json"
    if not path.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(path.read_text(encoding='utf-8'))
@router.post('/latest')
def latest(payload: LatestReq):
    pid=_v(payload.pool_id,'pool_id'); root=Path('ca_data')/'atlas'/'multi_item_supervised_status'/pid
    files=sorted(root.glob('multistatus_*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding='utf-8'))
