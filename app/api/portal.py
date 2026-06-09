from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.portal.catalog import PortalCatalogError, PortalCatalogService
from app.portal.contracts import PORTAL_SCHEMA_VERSION, PortalRunMode, PortalRunRequest
from app.portal.runtime import PortalRuntimeError, PortalRuntimeService


router = APIRouter(prefix="/api/portal", tags=["portal"])


class PortalArchivePathRequest(BaseModel):
    archive_path: str = Field(min_length=1)


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
