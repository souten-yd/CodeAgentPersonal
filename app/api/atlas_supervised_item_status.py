from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_supervised_item_status_policies import list_supervised_item_status_policies
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService

router = APIRouter(prefix="/api/atlas/supervised-item-status", tags=["atlas-supervised-item-status"])
class LatestReq(BaseModel):
    pool_id: str

def _v(value: str, field: str):
    try: return validate_relative_path(value)
    except Exception as exc: raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":f"invalid_{field}:{exc}"})

@router.get("/policies")
def policies():
    return {"policies":[p.model_dump() for p in list_supervised_item_status_policies()]}

@router.post("/finalize")
def finalize(payload: AtlasSupervisedItemStatusFinalizeRequest):
    payload.pool_id=_v(payload.pool_id,"pool_id"); payload.item_id=_v(payload.item_id,"item_id")
    if payload.run_id: payload.run_id=_v(payload.run_id,"run_id")
    if payload.source_run_id: payload.source_run_id=_v(payload.source_run_id,"source_run_id")
    return AtlasSupervisedItemStatusService().finalize(payload).model_dump()

@router.get("/results/{pool_id}/{finalize_run_id}")
def result(pool_id: str, finalize_run_id: str):
    pid=_v(pool_id,"pool_id")
    if not finalize_run_id.startswith("itemstatus_"): raise HTTPException(status_code=400, detail={"error":"invalid_request","reason":"invalid_finalize_run_id"})
    path = Path("ca_data") / "atlas" / "supervised_item_status" / pid / f"{_v(finalize_run_id,'finalize_run_id')}.json"
    if not path.exists(): raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))

@router.post("/latest")
def latest(payload: LatestReq):
    root = Path("ca_data") / "atlas" / "supervised_item_status" / _v(payload.pool_id,"pool_id")
    files = sorted(root.glob("itemstatus_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    if not files: raise HTTPException(status_code=404, detail={"error":"result_not_found","reason":"result_not_found"})
    return json.loads(files[0].read_text(encoding="utf-8"))
