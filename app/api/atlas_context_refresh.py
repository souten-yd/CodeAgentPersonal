from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_context_refresh_policies import list_context_refresh_policies
from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_context_refresh_service import AtlasContextRefreshService

router = APIRouter(prefix="/api/atlas/context-refresh", tags=["atlas-context-refresh"])
_svc = AtlasContextRefreshService()


class AtlasContextRefreshLatestRequest(BaseModel):
    pool_id: str


def _validate_id(value: str, field: str, prefix: str = "") -> str:
    try:
        safe = validate_relative_path(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}:{exc}"}) from exc
    if not safe or (prefix and not safe.startswith(prefix)):
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": f"invalid_{field}"})
    return safe


@router.get("/policies")
def get_policies():
    return {"policies": [p.model_dump() for p in list_context_refresh_policies()]}


@router.post("/run")
def run_context_refresh(payload: AtlasContextRefreshRequest):
    try:
        return _svc.refresh(payload).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": str(exc)}) from exc


@router.get("/bundles/{pool_id}/{bundle_id}")
def get_bundle(pool_id: str, bundle_id: str):
    safe_pool = _validate_id(pool_id, "pool_id")
    safe_bundle = _validate_id(bundle_id, "bundle_id", prefix="ctx_")
    path = Path("ca_data") / "atlas" / "context_bundles" / safe_pool / f"{safe_bundle}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "bundle_not_found", "reason": "bundle_not_found"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/latest")
def get_latest(payload: AtlasContextRefreshLatestRequest):
    safe_pool = _validate_id(payload.pool_id, "pool_id")
    root = Path("ca_data") / "atlas" / "context_bundles" / safe_pool
    if not root.exists():
        raise HTTPException(status_code=404, detail={"error": "bundle_not_found", "reason": "bundle_not_found"})
    latest = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not latest:
        raise HTTPException(status_code=404, detail={"error": "bundle_not_found", "reason": "bundle_not_found"})
    return json.loads(latest[0].read_text(encoding="utf-8"))
