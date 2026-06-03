from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_automation_features import (
    get_default_automation_features,
    load_full_automation_state,
    save_full_automation_state,
)
from agent.atlas_capability_preference_schema import get_default_preferences

router = APIRouter(prefix="/api/atlas/automation-features", tags=["atlas-automation-features"])


class AtlasAutomationFeaturesUpdate(BaseModel):
    features: dict = Field(default_factory=dict)
    selected_preset_id: str | None = None
    capability_preferences: dict | None = None


@router.get("")
def get_features(request: Request):
    root = resolve_atlas_ca_data_root(request)
    state = load_full_automation_state(root)
    return {
        **state,
        "defaults": get_default_automation_features(),
        "capability_defaults": get_default_preferences(),
    }


@router.post("")
def set_features(payload: AtlasAutomationFeaturesUpdate, request: Request):
    root = resolve_atlas_ca_data_root(request)
    return save_full_automation_state(
        root,
        features=payload.features,
        selected_preset_id=payload.selected_preset_id,
        capability_preferences=payload.capability_preferences,
    )
