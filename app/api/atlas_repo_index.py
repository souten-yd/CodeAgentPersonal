from __future__ import annotations
import re
from fastapi import APIRouter, HTTPException, Request
from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_repo_index_schema import AtlasRepoIndexRequest
from agent.project_intelligence.adapters.repo_index import ProjectIntelligenceRepoIndexAdapter

router=APIRouter(prefix='/api/atlas/repo-index',tags=['atlas-repo-index'])
_HASH_RE=re.compile(r"^[0-9a-f]{8,64}$")

def _svc(req:Request): return ProjectIntelligenceRepoIndexAdapter(resolve_atlas_ca_data_root(req))
def _bad(reason:str): raise HTTPException(status_code=400, detail={'error':'invalid_request','reason':reason})
def _validate_project_path(path:str):
    from pathlib import Path
    if not (path or '').strip(): _bad('project_path is required')
    p=Path(path).expanduser().resolve()
    if not p.exists(): _bad('project_path does not exist')
    if p.is_file(): _bad('project_path must be a directory')

@router.get('/policies')
def policies(request:Request): return _svc(request).policies()
@router.post('/build')
def build(payload:AtlasRepoIndexRequest, request:Request):
    _validate_project_path(payload.project_path)
    try:return _svc(request).build_or_update(payload).model_dump()
    except ValueError as e: raise HTTPException(status_code=400, detail={'error':'invalid_request','reason':str(e)})
@router.post('/impacts')
def impacts(payload:AtlasRepoIndexRequest, request:Request): _validate_project_path(payload.project_path); return _svc(request).query_impacts(payload)
@router.post('/related-tests')
def related(payload:AtlasRepoIndexRequest, request:Request): _validate_project_path(payload.project_path); return _svc(request).query_related_tests(payload)
@router.post('/latest')
def latest(payload:AtlasRepoIndexRequest, request:Request): _validate_project_path(payload.project_path); return _svc(request).load_latest(payload)
@router.get('/results/{project_hash}/{index_run_id}')
def result(project_hash:str,index_run_id:str,request:Request):
    if not _HASH_RE.fullmatch(project_hash or ''): _bad('invalid project_hash')
    if not index_run_id.startswith('repoindex_'): _bad('invalid index_run_id')
    data=_svc(request).load_result_by_hash(project_hash,index_run_id)
    if not data: raise HTTPException(status_code=404,detail={'error':'not_found','reason':'result not found'})
    return data
