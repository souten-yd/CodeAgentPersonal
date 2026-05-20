from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_repo_context_service import AtlasRepoContextService
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/atlas/repo-context", tags=["atlas-repo-context"])


def _validate_project_path(path: str) -> None:
    if not (path or "").strip():
        return
    p = Path(path).expanduser().resolve()
    if p.exists() and p.is_file():
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": "project_path must be directory"})


@router.get("/policies")
def get_policies():
    return {"allow_build_if_missing_default": False, "max_impacted_files": 100, "max_related_tests": 50}


@router.post("/snapshot")
def get_snapshot(payload: AtlasRepoContextRequest, request: Request):
    _validate_project_path(payload.project_path)
    svc = AtlasRepoContextService(data_root=resolve_atlas_ca_data_root(request))
    return svc.build_snapshot(payload).model_dump()


@router.post("/scope-summary")
def get_scope_summary(payload: AtlasRepoContextRequest, request: Request):
    _validate_project_path(payload.project_path)
    svc = AtlasRepoContextService(data_root=resolve_atlas_ca_data_root(request))
    return svc.build_plan_scope_summary(payload).model_dump()
