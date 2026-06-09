from __future__ import annotations

from fastapi import APIRouter

from app.portal.contracts import PORTAL_SCHEMA_VERSION, PortalRunMode


router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("/capabilities")
def get_portal_capabilities() -> dict:
    """Expose PR-PPC-0 Portal contracts only; no import, export, or run capability."""
    return {
        "schema_version": PORTAL_SCHEMA_VERSION,
        "run_modes": [mode.value for mode in PortalRunMode],
        "catalog_enabled": False,
        "import_enabled": False,
        "export_enabled": False,
        "run_enabled": False,
        "data_management_enabled": False,
        "package_export_includes_runtime_data": False,
    }
