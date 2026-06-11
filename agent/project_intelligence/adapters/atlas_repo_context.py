"""Compatibility adapter for Atlas repository-context API services.

The retained repo-context, impact, planner-packaging, and verification-recommendation
services stay behind this Project Intelligence adapter while API consumers stop importing
legacy owners directly.
"""

from __future__ import annotations

from pathlib import Path

from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMapRequest
from agent.atlas_plan_item_impact_map_service import AtlasPlanItemImpactMapService
from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request
from agent.atlas_repo_context_planner_packager import AtlasRepoContextPlannerPackager
from agent.atlas_repo_context_schema import (
    AtlasPlanScopeSummary,
    AtlasRepoContextRequest,
    AtlasRepoContextSnapshot,
)
from agent.atlas_repo_context_service import AtlasRepoContextService
from agent.atlas_verification_planning_schema import AtlasVerificationPlanningRequest
from agent.atlas_verification_planning_service import AtlasVerificationPlanningService
from agent.atlas_verification_recommendation_handoff_schema import AtlasVerificationRecommendationHandoffRequest
from agent.atlas_verification_recommendation_handoff_service import AtlasVerificationRecommendationHandoffService
from agent.atlas_verification_recommendation_schema import AtlasVerificationRecommendationRequest
from agent.atlas_verification_recommendation_service import AtlasVerificationRecommendationService
from agent.project_intelligence.adapters.planner_packaging_v2 import ProjectIntelligencePlannerPackagingV2Adapter


class AtlasRepoContextAdapter:
    """Read-only adapter used by repo-context API routes."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)

    def build_snapshot(self, request: AtlasRepoContextRequest) -> AtlasRepoContextSnapshot:
        return AtlasRepoContextService(data_root=self.data_root).build_snapshot(request)

    def build_plan_scope_summary(self, request: AtlasRepoContextRequest) -> AtlasPlanScopeSummary:
        return AtlasRepoContextService(data_root=self.data_root).build_plan_scope_summary(request)

    def build_impacted_test_recommendation(self, request: AtlasRepoContextRequest):
        return AtlasRepoContextPlannerPackager(data_root=self.data_root).build_impacted_test_recommendation(request)

    def build_repo_context_package(self, request: AtlasRepoContextRequest):
        return AtlasRepoContextPlannerPackager(data_root=self.data_root).build_package(request)

    def build_verification_plan(self, request: AtlasVerificationPlanningRequest):
        packager = AtlasRepoContextPlannerPackager(data_root=self.data_root)
        return AtlasVerificationPlanningService(data_root=self.data_root, packager=packager).build_plan(request)

    def build_plan_item_impact_map(self, request: AtlasPlanItemImpactMapRequest):
        return AtlasPlanItemImpactMapService(data_root=self.data_root).build_map(request)

    def build_planner_packaging_v2(self, request: AtlasPlannerPackagingV2Request):
        return ProjectIntelligencePlannerPackagingV2Adapter(data_root=self.data_root).build_package(request)

    def build_verification_recommendation(self, request: AtlasVerificationRecommendationRequest):
        return AtlasVerificationRecommendationService(data_root=self.data_root).recommend(request)

    def build_verification_recommendation_handoff(self, request: AtlasVerificationRecommendationHandoffRequest):
        return AtlasVerificationRecommendationHandoffService(data_root=self.data_root).build_handoff(request)
