from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_automation_features import (
    get_default_automation_features,
    load_automation_features,
    save_automation_features,
)

router = APIRouter(prefix="/api/atlas/automation-features", tags=["atlas-automation-features"])


class AtlasAutomationFeaturesUpdate(BaseModel):
    features: dict = Field(default_factory=dict)


@router.get("")
def get_features(request: Request):
    root = resolve_atlas_ca_data_root(request)
    return {"features": load_automation_features(root), "defaults": get_default_automation_features()}


@router.post("")
def set_features(payload: AtlasAutomationFeaturesUpdate, request: Request):
    root = resolve_atlas_ca_data_root(request)
    saved = save_automation_features(root, payload.features)
    return {"features": saved}
