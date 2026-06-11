from __future__ import annotations

import os
import string
from pathlib import Path

from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.env_detection import detect_runpod
from app.portal.catalog import PortalCatalogError, PortalCatalogService
from app.portal.contracts import PORTAL_SCHEMA_VERSION, PortalRunMode, PortalRunRequest
from app.portal.runtime import PortalRuntimeError, PortalRuntimeService


router = APIRouter(prefix="/api/portal", tags=["portal"])


class PortalArchivePathRequest(BaseModel):
    archive_path: str = Field(min_length=1)


class PortalImportBrowseRequest(BaseModel):
    path: str = ""


class PortalForkRequest(BaseModel):
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    new_project_id: str = Field(min_length=1)


class PortalInstallRequest(BaseModel):
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    installation_id: str | None = None


class PortalSnapshotRequest(BaseModel):
    snapshot_id: str | None = None


class PortalDeleteDataRequest(BaseModel):
    confirm_delete_data: bool = False


class PortalReconnectRequest(BaseModel):
    reconnect_token: str = Field(min_length=1)


def _catalog(request: Request) -> PortalCatalogService:
    return PortalCatalogService(resolve_atlas_ca_data_root(request))


def _raise_catalog_error(exc: PortalCatalogError) -> None:
    status = 404 if exc.code == "package_not_found" else 400
    raise HTTPException(status_code=status, detail={"error": exc.code}) from exc


def _runtime(request: Request) -> PortalRuntimeService:
    return PortalRuntimeService(resolve_atlas_ca_data_root(request))


def _raise_runtime_error(exc: PortalRuntimeError) -> None:
    status = 404 if exc.code in {"installation_not_found", "package_not_found", "portal_runtime_not_found", "snapshot_not_found"} else 400
    raise HTTPException(status_code=status, detail={"error": exc.code}) from exc


@router.get("/capabilities")
def get_portal_capabilities() -> dict:
    """Expose PR-PPC-0 Portal contracts only; no import, export, or run capability."""
    return {
        "schema_version": PORTAL_SCHEMA_VERSION,
        "run_modes": [mode.value for mode in PortalRunMode],
        "catalog_enabled": True,
        "import_enabled": True,
        "export_enabled": True,
        "run_enabled": True,
        "data_management_enabled": True,
        "package_export_includes_runtime_data": False,
    }


@router.get("/catalog")
def list_catalog(request: Request) -> dict:
    return _catalog(request).list_packages()


@router.post("/import/preflight")
def preflight_import(payload: PortalArchivePathRequest, request: Request) -> dict:
    try:
        return _catalog(request).preflight_archive(payload.archive_path)
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)


@router.post("/import")
def import_package(payload: PortalArchivePathRequest, request: Request) -> dict:
    try:
        return _catalog(request).import_archive(payload.archive_path)
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)


# Cap the uploaded (compressed) archive before it is opened. The catalog preflight
# additionally enforces uncompressed size, file count, and compression-ratio limits.
MAX_IMPORT_UPLOAD_BYTES = 100 * 1024 * 1024


@router.post("/import/upload")
async def import_upload(request: Request, file: UploadFile = File(...)) -> dict:
    """Browser/server upload import: stage the uploaded archive into a quarantine
    directory under a sanitized name, then run the same preflight + manifest +
    checksum checks as path import. The package is never trusted until those pass;
    classification stays untrusted_imported_package."""
    catalog = _catalog(request)
    import_id = uuid4().hex
    try:
        staged = catalog.begin_quarantine_import(import_id, file.filename or "")
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)
    try:
        size = 0
        with open(staged, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_IMPORT_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail={"error": "upload_too_large"})
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail={"error": "empty_upload"})
        return catalog.import_archive(str(staged))
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)
    finally:
        catalog.discard_quarantine_import(import_id)


def _import_browse_platform() -> str:
    if os.name == "nt":
        return "windows"
    return "runpod" if detect_runpod() else "linux"


def _import_browse_roots() -> list[dict]:
    """Environment-appropriate quick-access roots for the import folder picker.

    Windows exposes drive letters + the user home; Linux/RunPod exposes the
    RunPod /workspace mount, the user home, and the filesystem root."""
    roots: list[dict] = []
    home = str(Path.home())
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append({"label": f"{letter}:", "path": drive})
        roots.append({"label": "ホーム", "path": home})
    else:
        if os.path.isdir("/workspace"):
            roots.append({"label": "Workspace", "path": "/workspace"})
        roots.append({"label": "ホーム", "path": home})
        roots.append({"label": "ルート", "path": "/"})
    return roots


def _import_browse_default() -> str:
    if os.name != "nt" and os.path.isdir("/workspace"):
        return "/workspace"
    return str(Path.home())


@router.post("/import/browse")
def browse_import(payload: PortalImportBrowseRequest) -> dict:
    """Read-only directory listing so the Portal import UI can show an
    environment-appropriate folder picker instead of asking the user to type a
    server path. Returns sub-directories and .zip/.portal.zip archives only."""
    requested = (payload.path or "").strip()
    target = Path(requested).expanduser() if requested else Path(_import_browse_default())
    try:
        target = target.resolve()
    except Exception:
        pass
    parent = str(target.parent) if target.parent != target else ""
    result = {
        "schema_version": PORTAL_SCHEMA_VERSION,
        "platform": _import_browse_platform(),
        "roots": _import_browse_roots(),
        "default_path": _import_browse_default(),
        "path": str(target),
        "parent": parent,
        "entries": [],
        "error": "",
    }
    if not target.exists() or not target.is_dir():
        result["error"] = "directory_not_found"
        return result
    entries: list[dict] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not _safe_is_dir(p), p.name.lower()))
    except PermissionError:
        result["error"] = "permission_denied"
        return result
    except OSError:
        result["error"] = "directory_unreadable"
        return result
    for child in children:
        is_dir = _safe_is_dir(child)
        low = child.name.lower()
        is_zip = (not is_dir) and (low.endswith(".portal.zip") or low.endswith(".zip"))
        if not is_dir and not is_zip:
            continue
        entries.append({"name": child.name, "path": str(child), "is_dir": is_dir, "is_zip": is_zip})
    result["entries"] = entries[:2000]
    return result


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


@router.get("/packages/{package_id}/{version}/{content_hash}/export")
def export_package(package_id: str, version: str, content_hash: str, request: Request):
    try:
        path = _catalog(request).export_package_path(package_id, version, content_hash)
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)
    return FileResponse(str(path), media_type="application/zip", filename=path.name)


@router.delete("/packages/{package_id}/{version}/{content_hash}")
def uninstall_package(package_id: str, version: str, content_hash: str, request: Request) -> dict:
    try:
        return _catalog(request).uninstall_package(package_id, version, content_hash)
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)


@router.post("/fork-to-atlas")
def fork_to_atlas(payload: PortalForkRequest, request: Request) -> dict:
    try:
        return _catalog(request).fork_to_atlas(payload.package_id, payload.version, payload.content_hash, payload.new_project_id)
    except PortalCatalogError as exc:
        _raise_catalog_error(exc)


@router.post("/install")
def install_package(payload: PortalInstallRequest, request: Request) -> dict:
    try:
        return _runtime(request).install_package(payload.package_id, payload.version, payload.content_hash, payload.installation_id)
    except (PortalRuntimeError, PortalCatalogError) as exc:
        if isinstance(exc, PortalCatalogError):
            _raise_catalog_error(exc)
        _raise_runtime_error(exc)


@router.post("/run")
def run_portal(payload: PortalRunRequest, request: Request) -> dict:
    try:
        return _runtime(request).run(payload)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/stop")
def stop_portal_run(play_session_id: str, request: Request) -> dict:
    try:
        return _runtime(request).stop(play_session_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/purge")
def purge_portal_run(play_session_id: str, request: Request) -> dict:
    try:
        return _runtime(request).purge(play_session_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.get("/installations/{installation_id}/data")
def get_installation_data(installation_id: str, request: Request) -> dict:
    try:
        return _runtime(request).data_summary(installation_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.get("/installations/{installation_id}/snapshots")
def list_installation_snapshots(installation_id: str, request: Request) -> dict:
    """Focused snapshot list for the run sheet's Start-from-snapshot selector.
    Empty list is a valid, truthful state (no snapshots saved yet)."""
    try:
        summary = _runtime(request).data_summary(installation_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)
    snapshots = [
        {
            "snapshot_id": s.get("snapshot_id", ""),
            "source": s.get("source", ""),
            "last_modified": ((s.get("data") or {}).get("last_modified", "")),
            "data_bytes": ((s.get("data") or {}).get("bytes", 0)),
        }
        for s in (summary.get("snapshots") or [])
        if s.get("snapshot_id")
    ]
    return {
        "schema_version": PORTAL_SCHEMA_VERSION,
        "installation_id": installation_id,
        "available": True,
        "snapshots": snapshots,
    }


@router.get("/installations/{installation_id}/data/backup")
def export_installation_data_backup(installation_id: str, request: Request):
    try:
        path = _runtime(request).data_backup_path(installation_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)
    return FileResponse(str(path), media_type="application/zip", filename=path.name)


@router.delete("/installations/{installation_id}/data")
def delete_installation_data(installation_id: str, payload: PortalDeleteDataRequest, request: Request) -> dict:
    try:
        return _runtime(request).delete_data(installation_id, confirm_delete_data=payload.confirm_delete_data)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/data/save")
def save_portal_run_data(play_session_id: str, request: Request) -> dict:
    try:
        return _runtime(request).save_and_exit(play_session_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/data/snapshot")
def save_portal_run_snapshot(play_session_id: str, payload: PortalSnapshotRequest, request: Request) -> dict:
    try:
        return _runtime(request).save_snapshot_and_exit(play_session_id, payload.snapshot_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/data/discard")
def discard_portal_run_data(play_session_id: str, request: Request) -> dict:
    try:
        return _runtime(request).discard_and_exit(play_session_id)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/heartbeat")
def heartbeat_portal_run(play_session_id: str, payload: PortalReconnectRequest, request: Request) -> dict:
    try:
        return _runtime(request).heartbeat(play_session_id, payload.reconnect_token)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/disconnect")
def disconnect_portal_run(play_session_id: str, payload: PortalReconnectRequest, request: Request) -> dict:
    try:
        return _runtime(request).disconnect(play_session_id, payload.reconnect_token)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/runs/{play_session_id}/resume")
def resume_portal_run(play_session_id: str, payload: PortalReconnectRequest, request: Request) -> dict:
    try:
        return _runtime(request).resume(play_session_id, payload.reconnect_token)
    except PortalRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/recoveries/expire")
def expire_portal_recoveries(request: Request) -> dict:
    expired = _runtime(request).expire_recoveries()
    return {"schema_version": PORTAL_SCHEMA_VERSION, "status": "expired", "recoveries": expired}
