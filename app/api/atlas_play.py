from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.play.contracts import (
    PLAY_SCHEMA_VERSION,
    PLAY_THREAT_MODEL_VERSION,
    LaunchKind,
    PlayResourceLimits,
    PlayThreatModel,
    LaunchProfile,
)
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.file_service import PlayWorkspaceFileService
from app.atlas.play.paths import AtlasPlayPathLayout
from app.atlas.play.sessions import PlaySessionError, PlaySessionManager, reconcile_play_startup_orphans
from app.atlas.play.target_discovery import (
    PlayTargetResolutionRequest,
    resolve_play_target,
)


router = APIRouter(prefix="/api/atlas/play", tags=["atlas-play"])


class WorkspaceListRequest(BaseModel):
    project_id: str = Field(min_length=1)
    directory: str = "."
    limit: int = Field(default=200, ge=1, le=1000)


class WorkspaceReadRequest(BaseModel):
    project_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)


class WorkspaceWriteRequest(BaseModel):
    project_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    content: str = ""
    expected_sha256: str = Field(min_length=1)


class EnvironmentResolveRequest(BaseModel):
    project_id: str = Field(min_length=1)
    launch_profile: LaunchProfile


class SessionStartRequest(BaseModel):
    project_id: str = Field(min_length=1)
    launch_profile: LaunchProfile
    max_session_seconds: int | None = Field(default=None, ge=1)


def _project_work_root(request: Request, project_id: str):
    root = resolve_atlas_ca_data_root(request)
    try:
        work_root = AtlasPlayPathLayout(root).atlas_project_work_root(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_project_id", "reason": str(exc)}) from exc
    if not work_root.exists() or not work_root.is_dir():
        raise HTTPException(status_code=404, detail={"error": "not_found", "reason": "project_work_root_missing"})
    return work_root


def _persist_target_resolution(request: Request, payload: PlayTargetResolutionRequest, result: dict) -> None:
    root = resolve_atlas_ca_data_root(request)
    target_dir = AtlasPlayPathLayout(root).play_target_graph_root(payload.project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "atlas.play.target_graph_record.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": payload.project_id,
        "source": payload.source,
        "resolution": result,
    }
    (target_dir / "latest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def _raise_if_not_success(result: dict) -> None:
    status = str(result.get("status") or "")
    if status in {"ok", "written"}:
        return
    reason = str(result.get("reason") or "workspace_file_request_failed")
    if status == "conflict":
        raise HTTPException(status_code=409, detail={"error": "conflict", **result})
    if reason in {"file_missing", "directory_missing"}:
        raise HTTPException(status_code=404, detail={"error": "not_found", **result})
    raise HTTPException(status_code=400, detail={"error": "invalid_request", **result})


def _session_manager(request: Request) -> PlaySessionManager:
    return PlaySessionManager(resolve_atlas_ca_data_root(request))


def _raise_session_error(exc: PlaySessionError) -> None:
    status = 404 if exc.code == "session_not_found" else 400
    raise HTTPException(status_code=status, detail={"error": exc.code}) from exc


@router.get("/capabilities")
def get_atlas_play_capabilities() -> dict:
    """Expose PR-PPC-0 contracts only; no launch or file-serving capability."""
    return {
        "schema_version": PLAY_SCHEMA_VERSION,
        "threat_model_schema_version": PLAY_THREAT_MODEL_VERSION,
        "launch_kinds": [kind.value for kind in LaunchKind],
        "resource_limits": PlayResourceLimits().model_dump(),
        "threat_model": PlayThreatModel().model_dump(),
        "execution_enabled": True,
        "file_serving_enabled": False,
        "process_supervisor_enabled": True,
        "preview_gateway_enabled": False,
    }


@router.post("/workspace/files/list")
def list_workspace_files(payload: WorkspaceListRequest, request: Request) -> dict:
    service = PlayWorkspaceFileService(project_root=_project_work_root(request, payload.project_id))
    result = service.list_files(directory=payload.directory, limit=payload.limit)
    _raise_if_not_success(result)
    return result


@router.post("/workspace/files/read")
def read_workspace_file(payload: WorkspaceReadRequest, request: Request) -> dict:
    service = PlayWorkspaceFileService(project_root=_project_work_root(request, payload.project_id))
    result = service.read_file(relative_path=payload.relative_path)
    _raise_if_not_success(result)
    return result


@router.post("/workspace/files/write")
def write_workspace_file(payload: WorkspaceWriteRequest, request: Request) -> dict:
    service = PlayWorkspaceFileService(project_root=_project_work_root(request, payload.project_id))
    result = service.write_file(
        relative_path=payload.relative_path,
        content=payload.content,
        expected_sha256=payload.expected_sha256,
    )
    _raise_if_not_success(result)
    return result


@router.post("/target/resolve")
def resolve_target(payload: PlayTargetResolutionRequest, request: Request) -> dict:
    work_root = _project_work_root(request, payload.project_id)
    result = resolve_play_target(work_root, payload).model_dump(mode="json")
    _persist_target_resolution(request, payload, result)
    return result


@router.post("/environment/resolve")
def resolve_environment(payload: EnvironmentResolveRequest, request: Request) -> dict:
    work_root = _project_work_root(request, payload.project_id)
    return build_structured_launch_adapter(work_root, payload.launch_profile).model_dump(mode="json")


@router.post("/sessions/start")
def start_session(payload: SessionStartRequest, request: Request) -> dict:
    work_root = _project_work_root(request, payload.project_id)
    adapter = build_structured_launch_adapter(work_root, payload.launch_profile)
    try:
        record = _session_manager(request).start_session(
            project_id=payload.project_id,
            project_root=work_root,
            adapter=adapter,
            max_session_seconds=payload.max_session_seconds,
        )
    except PlaySessionError as exc:
        _raise_session_error(exc)
    return record.model_dump(mode="json")


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict:
    try:
        return _session_manager(request).get_session(session_id).model_dump(mode="json")
    except PlaySessionError as exc:
        _raise_session_error(exc)


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str, request: Request) -> dict:
    try:
        return _session_manager(request).stop_session(session_id).model_dump(mode="json")
    except PlaySessionError as exc:
        _raise_session_error(exc)


@router.post("/sessions/{session_id}/restart")
def restart_session(session_id: str, request: Request) -> dict:
    try:
        return _session_manager(request).restart_session(session_id).model_dump(mode="json")
    except PlaySessionError as exc:
        _raise_session_error(exc)


@router.post("/sessions/{session_id}/purge")
def purge_session(session_id: str, request: Request) -> dict:
    try:
        return _session_manager(request).purge_session(session_id).model_dump(mode="json")
    except PlaySessionError as exc:
        _raise_session_error(exc)


@router.post("/sessions/reconcile")
def reconcile_sessions(request: Request) -> dict:
    records = reconcile_play_startup_orphans(resolve_atlas_ca_data_root(request))
    return {
        "schema_version": "atlas.play.session_reconcile.v1",
        "reconciled": [record.model_dump(mode="json") for record in records],
    }
