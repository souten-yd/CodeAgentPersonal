from __future__ import annotations

from pathlib import Path

from agent.atlas_verification_recommendation_handoff_schema import AtlasVerificationRecommendationHandoff, AtlasVerificationRecommendationHandoffRequest
from agent.atlas_verification_recommendation_schema import AtlasVerificationRecommendationRequest
from agent.atlas_verification_recommendation_service import AtlasVerificationRecommendationService


class AtlasVerificationRecommendationHandoffService:
    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).expanduser().resolve()

    def _limit(self, arr: list, n: int) -> list:
        return list(arr or [])[:n]

    def build_handoff(self, req: AtlasVerificationRecommendationHandoffRequest) -> AtlasVerificationRecommendationHandoff:
        warnings: list[str] = []
        errors: list[str] = []
        source = dict(req.verification_recommendation or {})
        plan_item = dict(req.plan_item or {})
        plan_item_md = plan_item.get("metadata") if isinstance(plan_item.get("metadata"), dict) else {}

        if req.item_id:
            item_rec = plan_item_md.get("verification_recommendation") if isinstance(plan_item_md, dict) else {}
            if isinstance(item_rec, dict) and item_rec:
                source = item_rec
            elif source:
                warnings.append("item_specific_verification_recommendation_unavailable")

        if not source and req.include_verification_recommendation:
            try:
                source = AtlasVerificationRecommendationService(data_root=self.data_root).recommend(
                    AtlasVerificationRecommendationRequest(
                        workspace_id=req.workspace_id,
                        project_path=req.project_path,
                        pool_id=req.pool_id,
                        item_id=req.item_id,
                        goal=req.goal,
                        plan_pool=req.plan_pool,
                        include_planner_packaging_v2=True,
                        allow_build_if_missing=False,
                    )
                ).model_dump()
            except Exception:
                warnings.append("verification_recommendation_build_failed")

        if not source:
            warnings.append("verification_recommendation_unavailable")

        impacted_files = self._limit(source.get("impacted_files", []), 20)
        related_tests = self._limit(source.get("related_tests", []), 15)
        recommended_commands = self._limit(source.get("recommended_commands", []), 5)
        manual_steps = self._limit(source.get("manual_verification_steps", []), 10)
        ci_hints = self._limit(source.get("ci_selection_hints", []), 10)
        warnings = self._limit([*warnings, *list(source.get("warnings", []))], 20)
        errors = self._limit(list(source.get("errors", [])), 10)
        confidence = str(source.get("confidence", "unknown") or "unknown")
        status = str(source.get("status", "missing") or "missing")
        summary = str(source.get("summary", "") or "")
        approval_summary = (
            f"status={status} confidence={confidence} impacted_files={len(impacted_files)} "
            f"related_tests={len(related_tests)} commands={len(recommended_commands)}. "
            "Manual approval only. Suggested commands were not executed."
        )
        handoff_md = {
            "source": "verification_recommendation",
            "item_id": req.item_id,
            "action_id": req.action_id,
            "confidence": confidence,
            "advisory_only": True,
            "commands_are_suggestions_only": True,
            "executed": False,
            "auto_verification_triggered": False,
            "auto_test_execution_triggered": False,
            "manual_approval_only": True,
        }
        metadata = {
            "advisory_only": True,
            "executed": False,
            "shell_executed": False,
            "remote_git_executed": False,
            "auto_verification_triggered": False,
            "auto_test_execution_triggered": False,
            "no_auto_build": True,
            "no_execution": True,
            "commands_are_suggestions_only": True,
            "verification_recommendation_handoff": True,
            "manual_approval_only": True,
            **dict(req.metadata or {}),
        }
        return AtlasVerificationRecommendationHandoff(
            status=status,
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            pool_id=req.pool_id,
            run_id=req.run_id,
            item_id=req.item_id,
            action_id=req.action_id,
            goal=req.goal,
            summary=summary,
            approval_summary=approval_summary,
            impacted_files=impacted_files,
            related_tests=related_tests,
            recommended_commands=recommended_commands,
            manual_verification_steps=manual_steps,
            ci_selection_hints=ci_hints,
            confidence=confidence,
            warnings=warnings,
            errors=errors,
            handoff_metadata=handoff_md,
            metadata=metadata,
        )
