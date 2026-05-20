from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_repo_index_schema import AtlasRepoIndexRequest
from agent.atlas_repo_index_policies import POLICIES
from agent.atlas_repo_index_service import AtlasRepoIndexService

router=APIRouter(prefix='/api/atlas/repo-index',tags=['atlas-repo-index'])

def _svc(req:Request): return AtlasRepoIndexService(resolve_atlas_ca_data_root(req))

@router.get('/policies')
def policies(): return {'policies':POLICIES}
@router.post('/build')
def build(payload:AtlasRepoIndexRequest, request:Request):
    try:return _svc(request).build_or_update(payload).model_dump()
    except ValueError as e: raise HTTPException(status_code=400, detail={'error':'invalid_request','reason':str(e)})
@router.post('/impacts')
def impacts(payload:AtlasRepoIndexRequest, request:Request): return _svc(request).query_impacts(payload.project_path,payload.changed_files)
@router.post('/related-tests')
def related(payload:AtlasRepoIndexRequest, request:Request): return _svc(request).query_related_tests(payload.project_path,payload.changed_files)
@router.post('/latest')
def latest(payload:AtlasRepoIndexRequest, request:Request): return _svc(request).load_latest(payload.workspace_id,payload.project_path)
@router.get('/results/{project_hash}/{index_run_id}')
def result(project_hash:str,index_run_id:str,request:Request):
    if not index_run_id.startswith('repoindex_'): raise HTTPException(status_code=400,detail={'error':'invalid_request','reason':'invalid index_run_id'})
    return {'project_hash':project_hash,'index_run_id':index_run_id}
