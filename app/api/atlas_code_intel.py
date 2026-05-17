from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest, AtlasRelatedTestsRequest, AtlasSymbolIndexRequest
from agent.atlas_code_intel_service import AtlasCodeIntelService

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
