from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent.atlas_dev_tool_schema import AtlasDevToolRequest
from agent.project_intelligence.adapters.atlas_inspection import AtlasInspectionAdapter

router = APIRouter(prefix="/api/atlas/dev-tools", tags=["atlas-dev-tools"])
_inspection = AtlasInspectionAdapter()


@router.post('/git-status')
def git_status(payload: AtlasDevToolRequest):
    try:
        return _inspection.git_status(payload.project_path).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/git-diff')
def git_diff(payload: AtlasDevToolRequest, staged: bool = False):
    try:
        return _inspection.git_diff(
            payload.project_path,
            payload.relative_path,
            staged=staged,
            max_bytes=payload.max_bytes,
        ).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/git-ls-files')
def git_ls_files(payload: AtlasDevToolRequest):
    try:
        return _inspection.git_ls_files(
            payload.project_path,
            max_files=payload.max_files,
            include_untracked=payload.include_untracked,
        ).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/project-tree')
def project_tree(payload: AtlasDevToolRequest, max_depth: int = 4):
    return _inspection.project_tree(payload.project_path, max_depth=max_depth, max_files=payload.max_files).model_dump()


@router.post('/list-files')
def list_files(payload: AtlasDevToolRequest, glob: str = ""):
    return _inspection.list_files(payload.project_path, glob=glob, max_files=payload.max_files).model_dump()


@router.post('/file-outline')
def file_outline(payload: AtlasDevToolRequest):
    try:
        return _inspection.file_outline(
            payload.project_path,
            payload.relative_path,
            max_bytes=payload.max_bytes,
        ).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
