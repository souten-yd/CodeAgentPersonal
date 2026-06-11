from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_verification_planning_schema import AtlasVerificationPlanningRequest
from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMapRequest
from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request
from agent.atlas_verification_recommendation_schema import AtlasVerificationRecommendationRequest
from agent.atlas_verification_recommendation_handoff_schema import AtlasVerificationRecommendationHandoffRequest
from agent.project_intelligence.adapters.atlas_repo_context import AtlasRepoContextAdapter
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/atlas/repo-context", tags=["atlas-repo-context"])


def _validate_project_path(path: str) -> None:
    if not (path or "").strip():
        return
    p = Path(path).expanduser().resolve()
    if p.exists() and p.is_file():
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": "project_path must be directory"})


@router.get("/policies")
def get_policies():
    return {"allow_build_if_missing_default": False, "max_impacted_files": 100, "max_related_tests": 50}


@router.post("/snapshot")
def get_snapshot(payload: AtlasRepoContextRequest, request: Request):
    _validate_project_path(payload.project_path)
    adapter = AtlasRepoContextAdapter(data_root=resolve_atlas_ca_data_root(request))
    return adapter.build_snapshot(payload).model_dump()


@router.post("/scope-summary")
def get_scope_summary(payload: AtlasRepoContextRequest, request: Request):
    _validate_project_path(payload.project_path)
    adapter = AtlasRepoContextAdapter(data_root=resolve_atlas_ca_data_root(request))
    return adapter.build_plan_scope_summary(payload).model_dump()


@router.post("/impacted-tests")
def impacted_tests(req: AtlasRepoContextRequest, request: Request):
    _validate_project_path(req.project_path)
    data_root = resolve_atlas_ca_data_root(request)
    return AtlasRepoContextAdapter(data_root=data_root).build_impacted_test_recommendation(req).model_dump()


@router.post("/verification-plan")
def verification_plan(req: AtlasVerificationPlanningRequest, request: Request):
    _validate_project_path(req.project_path)
    adapter = AtlasRepoContextAdapter(data_root=resolve_atlas_ca_data_root(request))
    return adapter.build_verification_plan(req).model_dump()



@router.post("/plan-item-impact-map")
def plan_item_impact_map(req: AtlasPlanItemImpactMapRequest, request: Request):
    _validate_project_path(req.project_path)
    adapter = AtlasRepoContextAdapter(data_root=resolve_atlas_ca_data_root(request))
    return adapter.build_plan_item_impact_map(req).model_dump()


@router.post("/planner-packaging-v2")
def planner_packaging_v2(req: AtlasPlannerPackagingV2Request, request: Request):
    path = (req.project_path or "").strip()
    if path:
        p = Path(path)
        if p.exists() and p.is_file():
            raise HTTPException(status_code=400, detail="project_path must be directory")
    data_root = resolve_atlas_ca_data_root(request)
    pkg = AtlasRepoContextAdapter(data_root=data_root).build_planner_packaging_v2(req)
    return pkg.model_dump()


@router.post("/verification-recommendation")
def verification_recommendation(req: AtlasVerificationRecommendationRequest, request: Request):
    _validate_project_path(req.project_path)
    data_root = resolve_atlas_ca_data_root(request)
    result = AtlasRepoContextAdapter(data_root=data_root).build_verification_recommendation(req)
    return result.model_dump()


@router.post("/verification-recommendation-handoff")
def verification_recommendation_handoff(req: AtlasVerificationRecommendationHandoffRequest, request: Request):
    _validate_project_path(req.project_path)
    data_root = resolve_atlas_ca_data_root(request)
    result = AtlasRepoContextAdapter(data_root=data_root).build_verification_recommendation_handoff(req)
    return result.model_dump()
