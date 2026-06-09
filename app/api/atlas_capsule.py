from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.capsule.builder import CapsuleBuildError, CapsuleBuilder
from app.atlas.capsule.contracts import CAPSULE_SCHEMA_VERSION, CapsuleBuildRequest


router = APIRouter(prefix="/api/atlas/capsule", tags=["atlas-capsule"])


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
        raise HTTPException(status_code=400, detail={"error": exc.code}) from exc
