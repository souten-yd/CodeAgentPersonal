from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.portal.catalog import PortalCatalogError, PortalCatalogService
from app.portal.contracts import PORTAL_SCHEMA_VERSION, PortalRunMode


router = APIRouter(prefix="/api/portal", tags=["portal"])


class PortalArchivePathRequest(BaseModel):
    archive_path: str = Field(min_length=1)


class PortalForkRequest(BaseModel):
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    new_project_id: str = Field(min_length=1)


def _catalog(request: Request) -> PortalCatalogService:
    return PortalCatalogService(resolve_atlas_ca_data_root(request))


def _raise_catalog_error(exc: PortalCatalogError) -> None:
    status = 404 if exc.code == "package_not_found" else 400
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
        "run_enabled": False,
        "data_management_enabled": False,
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
