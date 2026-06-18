from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.capsule.builder import CapsuleBuildError, CapsuleBuilder
from app.atlas.capsule.contracts import CAPSULE_SCHEMA_VERSION, CapsuleBuildRequest
from app.atlas.play.sessions import PlaySessionError


router = APIRouter(prefix="/api/atlas/capsule", tags=["atlas-capsule"])

_CAPSULE_ERROR_REASONS = {
    "invalid_package_id": "Package name must use only letters, numbers, dot, underscore, or dash.",
    "session_not_found": "Play session not found.",
    "session_project_mismatch": "Play session belongs to a different workspace.",
    "play_session_not_successful": "Session already stopped unsuccessfully or has not been stopped successfully.",
    "default_profile_not_selected": "Default launch profile is not selected.",
    "selected_profile_missing": "Selected launch profile is missing from the build request.",
    "composite_dependency_not_selected": "Composite launch profile dependency is not selected.",
    "no_package_files": "No package files were found in the workspace.",
    "stale_file_hash": "Workspace files changed since selection; reload Play files or use force build.",
}


@router.get("/capabilities")
def get_capsule_capabilities() -> dict:
    return {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "builder_enabled": True,
        "deterministic_archives": True,
        "runtime_data_included": False,
    }


@router.post("/build")
def build_capsule(payload: CapsuleBuildRequest, request: Request) -> dict:
    try:
        return CapsuleBuilder(resolve_atlas_ca_data_root(request)).build(payload)
    except CapsuleBuildError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code, "reason": _CAPSULE_ERROR_REASONS.get(exc.code, exc.code)},
        ) from exc
    except PlaySessionError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code, "reason": _CAPSULE_ERROR_REASONS.get(exc.code, exc.code)},
        ) from exc
