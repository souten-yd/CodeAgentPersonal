from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest, AtlasRelatedTestsRequest, AtlasSymbolIndexRequest
from agent.atlas_code_intel_service import AtlasCodeIntelService
from agent.atlas_repo_index_schema import AtlasRepoIndexRequest
from agent.atlas_repo_index_service import AtlasRepoIndexService
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/atlas/code-intel", tags=["atlas-code-intel"])
_svc = AtlasCodeIntelService()


@router.post('/symbol-index')
def symbol_index(payload: AtlasSymbolIndexRequest):
    try:
        return _svc.build_symbol_index(payload).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'error': 'invalid_request', 'reason': str(exc)}) from exc


@router.post('/dependency-graph')
def dependency_graph(payload: AtlasDependencyGraphRequest):
    try:
        return _svc.build_dependency_graph(payload).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'error': 'invalid_request', 'reason': str(exc)}) from exc


@router.post('/related-tests')
def related_tests(payload: AtlasRelatedTestsRequest):
    try:
        return _svc.find_related_tests(payload).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'error': 'invalid_request', 'reason': str(exc)}) from exc


def _repo_svc(request: Request):
    return AtlasRepoIndexService(resolve_atlas_ca_data_root(request))

@router.post('/symbol-index-v2')
def symbol_index_v2(payload: AtlasRepoIndexRequest, request: Request):
    return _repo_svc(request).build_or_update(payload).model_dump()
