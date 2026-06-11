from __future__ import annotations

from pathlib import Path

from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request
from agent.atlas_verification_recommendation_schema import (
    AtlasVerificationRecommendation,
    AtlasVerificationRecommendationRequest,
)
from agent.project_intelligence.adapters.planner_packaging_v2 import ProjectIntelligencePlannerPackagingV2Adapter


def _dedup_str(items: list) -> list[str]:
    out = []
    seen = set()
    for item in items or []:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _dedup_dict(items: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = tuple(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


class AtlasVerificationRecommendationService:
    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).expanduser().resolve()

    def _build_packaging_if_missing(self, req: AtlasVerificationRecommendationRequest, warnings: list[str], errors: list[str]) -> dict:
        if req.planner_packaging_v2:
            return dict(req.planner_packaging_v2)
        if not req.include_planner_packaging_v2:
            warnings.append("planner_packaging_v2_not_included")
            return {}
        try:
            built = ProjectIntelligencePlannerPackagingV2Adapter(data_root=self.data_root).build_package(
                AtlasPlannerPackagingV2Request(
                    workspace_id=req.workspace_id,
                    project_path=req.project_path,
                    pool_id=req.pool_id,
                    goal=req.goal,
                    changed_files=req.changed_files,
                    target_files=req.target_files,
                    plan_pool=req.plan_pool,
                    include_repo_context=True,
                    include_plan_item_impact_map=True,
                    include_context_refresh_v2=True,
                    allow_build_if_missing=False,
                )
            ).model_dump()
            return built
        except Exception as e:
            warnings.append("planner_packaging_v2_build_failed")
            errors.append(str(e))
            return {}

    def recommend(self, req: AtlasVerificationRecommendationRequest) -> AtlasVerificationRecommendation:
        warnings: list[str] = []
        errors: list[str] = []
        source = self._build_packaging_if_missing(req, warnings, errors)

        impacted_files = _dedup_str(list(source.get("impacted_files") or []))[:50]
        related_tests = _dedup_str(list(source.get("related_tests") or []))[:30]
        recommended_commands = _dedup_str(list(source.get("recommended_commands") or []))[:10]
        manual_steps = _dedup_str(list(source.get("manual_verification_steps") or []))[:20]
        ci_hints = _dedup_dict(list(source.get("ci_selection_hints") or []))[:20]
        evidence = _dedup_dict(list(source.get("evidence") or []))[:80]

        item_id = str(req.item_id or "").strip()
        if item_id:
            filtered_hints = [h for h in ci_hints if str(h.get("item_id") or "").strip() == item_id]
            filtered_evidence = [e for e in evidence if str(e.get("item_id") or "").strip() == item_id]
            if filtered_hints or filtered_evidence:
                ci_hints = filtered_hints or ci_hints
                evidence = filtered_evidence or evidence
            else:
                warnings.append("item_specific_recommendation_unavailable")

        status = str(source.get("status") or "missing")
        if not source:
            status = "missing"
            warnings.append("planner_packaging_v2_missing")
        elif warnings and status == "available":
            status = "partial"

        if not (impacted_files or related_tests or recommended_commands or manual_steps or ci_hints or evidence):
            status = "missing" if not source else "partial"

        return AtlasVerificationRecommendation(
            status=status,
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            pool_id=req.pool_id,
            item_id=req.item_id,
            goal=req.goal,
            summary="Manual verification recommendation generated from Planner Packaging v2. Commands are suggestions only and were not executed.",
            impacted_files=impacted_files,
            related_tests=related_tests,
            recommended_commands=recommended_commands,
            manual_verification_steps=manual_steps,
            ci_selection_hints=ci_hints,
            evidence=evidence,
            confidence=str(source.get("confidence") or "unknown"),
            warnings=_dedup_str(warnings)[:30],
            errors=_dedup_str(errors)[:20],
        )
