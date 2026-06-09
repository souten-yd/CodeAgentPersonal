from __future__ import annotations

from fastapi import APIRouter

from app.atlas.play.contracts import (
    PLAY_SCHEMA_VERSION,
    PLAY_THREAT_MODEL_VERSION,
    LaunchKind,
    PlayResourceLimits,
    PlayThreatModel,
)


router = APIRouter(prefix="/api/atlas/play", tags=["atlas-play"])


@router.get("/capabilities")
def get_atlas_play_capabilities() -> dict:
    """Expose PR-PPC-0 contracts only; no launch or file-serving capability."""
    return {
        "schema_version": PLAY_SCHEMA_VERSION,
        "threat_model_schema_version": PLAY_THREAT_MODEL_VERSION,
        "launch_kinds": [kind.value for kind in LaunchKind],
        "resource_limits": PlayResourceLimits().model_dump(),
        "threat_model": PlayThreatModel().model_dump(),
        "execution_enabled": False,
        "file_serving_enabled": False,
        "process_supervisor_enabled": False,
        "preview_gateway_enabled": False,
    }
