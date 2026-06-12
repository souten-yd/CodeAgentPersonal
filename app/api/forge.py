"""Forge backend API (PFG-19).

Read-mostly Forge surface for the UI. Composes the Forge service against the resolved
Atlas ca_data root. Secrets are never returned; disabled/unavailable provider states are
surfaced truthfully; mutating endpoints (stage/route policy, loadouts, arena run) never
bypass Safe Apply and never auto-cut-over production routing.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agent.model_forge.forge_service import ForgeService
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/forge", tags=["forge"])


def _service(request: Request) -> ForgeService:
    return ForgeService(resolve_atlas_ca_data_root(request))


class ArenaSpec(BaseModel):
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    route_id: str = Field(min_length=1)


class ArenaRunRequest(BaseModel):
    stage: str = Field(min_length=1)
    specs: list[ArenaSpec] = Field(default_factory=list)
    source_mode: str | None = None
    privacy_mode: str = "no_external_code"
    preset_id: str = ""
    task_id: str = ""


class StagePolicyRequest(BaseModel):
    stage: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    allow_production_routing: bool = False
    fixed_provider_id: str = ""
    fixed_model_id: str = ""
    fallback_provider_id: str = ""
    fallback_model_id: str = ""
    reason: str = ""


class RoutePolicyRequest(BaseModel):
    change_class: str = Field(min_length=1)
    preferred_route: str = Field(min_length=1)


class LoadoutRequest(BaseModel):
    loadout_id: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    source_mode: str = "local_only"
    stage_overrides: dict[str, str] = Field(default_factory=dict)
    provider_preferences: list[str] = Field(default_factory=list)
    risky: bool = False


@router.get("/status")
def get_status(request: Request) -> dict:
    return _service(request).status()


@router.get("/providers")
def get_providers(request: Request) -> dict:
    return {"providers": _service(request).providers()}


@router.get("/models")
def get_models(request: Request) -> dict:
    return {"models": _service(request).models()}


@router.get("/profiles")
def get_profiles(request: Request) -> dict:
    return {"profiles": _service(request).profiles_list()}


@router.get("/leaderboard")
def get_leaderboard(request: Request) -> dict:
    return {"leaderboard": _service(request).leaderboard()}


@router.get("/presets")
def get_presets(request: Request) -> dict:
    return {"presets": _service(request).presets()}


@router.post("/arena/run")
def post_arena_run(request: Request, body: ArenaRunRequest) -> dict:
    try:
        return _service(request).run_arena(
            stage=body.stage, specs=[s.model_dump() for s in body.specs],
            source_mode=body.source_mode, privacy_mode=body.privacy_mode,
            preset_id=body.preset_id, task_id=body.task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/arena/runs/{arena_run_id}")
def get_arena_run(request: Request, arena_run_id: str) -> dict:
    record = _service(request).get_arena_run(arena_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="arena_run_not_found")
    return record


@router.get("/stage-policy")
def get_stage_policy(request: Request) -> dict:
    return {"stage_policy": _service(request).get_stage_policy()}


@router.post("/stage-policy")
def post_stage_policy(request: Request, body: StagePolicyRequest) -> dict:
    try:
        return _service(request).set_stage_policy(**body.model_dump())
    except PermissionError as exc:
        # No automatic cutover: an active production-routing mode needs acknowledgement.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/route-policy")
def get_route_policy(request: Request) -> dict:
    return {"route_policy": _service(request).get_route_policy()}


@router.post("/route-policy")
def post_route_policy(request: Request, body: RoutePolicyRequest) -> dict:
    try:
        return _service(request).set_route_policy(
            change_class=body.change_class, preferred_route=body.preferred_route,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loadouts")
def get_loadouts(request: Request) -> dict:
    return {"loadouts": _service(request).get_loadouts()}


@router.post("/loadouts")
def post_loadout(request: Request, body: LoadoutRequest) -> dict:
    try:
        return _service(request).save_loadout(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
