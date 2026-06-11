"""Project Intelligence plan-item impact-map adapter.

This retained implementation replaces the retired legacy
``AtlasPlanItemImpactMapService`` owner while preserving advisory, non-executing
impact-map behavior.
"""

from __future__ import annotations

from pathlib import Path

from agent.atlas_plan_item_impact_map_schema import (
    AtlasPlanItemImpact,
    AtlasPlanItemImpactMap,
    AtlasPlanItemImpactMapRequest,
)
from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_verification_planning_schema import AtlasVerificationPlanningRequest
from agent.atlas_verification_planning_service import AtlasVerificationPlanningService
from agent.project_intelligence.adapters.repo_context_packaging import ProjectIntelligenceRepoContextPackager


class ProjectIntelligencePlanItemImpactMapAdapter:
    """Build advisory impact maps from repo context and verification planning hints."""

    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).expanduser().resolve()
        self.packager = ProjectIntelligenceRepoContextPackager(data_root=self.data_root)
        self.verification = AtlasVerificationPlanningService(data_root=self.data_root, packager=self.packager)

    def build_map(self, req: AtlasPlanItemImpactMapRequest) -> AtlasPlanItemImpactMap:
        plan_pool = dict(req.plan_pool or {})
        items = list(plan_pool.get("items") or [])
        if not items:
            status = "empty_plan_pool" if "items" in plan_pool else "missing"
            return AtlasPlanItemImpactMap(
                status=status,
                workspace_id=req.workspace_id,
                project_path=req.project_path,
                pool_id=req.pool_id,
                goal=req.goal,
                warnings=["plan_pool_items_missing_non_blocking"],
            )

        changed_files = list(req.changed_files or [])
        target_files = list(req.target_files or [])
        repo_req = AtlasRepoContextRequest(
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            goal=req.goal,
            changed_files=changed_files,
            target_files=target_files,
            allow_build_if_missing=False,
            mode="scope_summary",
        )
        pkg = self.packager.build_package(repo_req)
        verify = self.verification.build_plan(
            AtlasVerificationPlanningRequest(
                workspace_id=req.workspace_id,
                project_path=req.project_path,
                goal=req.goal,
                changed_files=changed_files,
                target_files=target_files,
                allow_build_if_missing=False,
            )
        )
        global_impacted = list(pkg.impacted_files or [])[:100]
        global_tests = list(verify.related_tests or [])[:50]
        impacts: list[AtlasPlanItemImpact] = []
        for item in items:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            repo_metadata = metadata.get("repo_context") if isinstance(metadata.get("repo_context"), dict) else {}
            item_targets = list(
                dict.fromkeys(list(item.get("target_files") or []) + list(repo_metadata.get("target_files") or []))
            )
            if not item_targets:
                item_targets = target_files[:]
            item_impacted, item_tests, reasons, confidence = self._match(
                item_targets, changed_files, global_impacted, global_tests
            )
            item_commands = self._commands_for_tests(item_tests)
            impacts.append(
                AtlasPlanItemImpact(
                    item_id=str(item.get("item_id") or ""),
                    title=str(item.get("title") or ""),
                    action_type=str(item.get("action_type") or ""),
                    risk_level=str(item.get("risk_level") or ""),
                    target_files=item_targets[:30],
                    changed_files=changed_files[:30],
                    impacted_files=item_impacted[:30],
                    related_tests=item_tests[:15],
                    impacted_symbols=list(repo_metadata.get("impacted_symbols") or [])[:30],
                    recommended_commands=item_commands[:5],
                    manual_verification_steps=[
                        "Review attached impacted files.",
                        "Run suggested tests manually.",
                        "Validate CI hints manually.",
                    ][:5],
                    ci_selection_hints=list(
                        verify.ci_selection_hints and [hint.model_dump() for hint in verify.ci_selection_hints] or []
                    )[:5],
                    confidence=confidence,
                    reasons=reasons,
                    warnings=[] if item_impacted else ["no_item_specific_impact_found_used_global_fallback"],
                )
            )

        return AtlasPlanItemImpactMap(
            status="available" if impacts else "missing",
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            pool_id=req.pool_id,
            goal=req.goal,
            item_count=len(impacts),
            impacts=impacts,
            global_impacted_files=global_impacted[:100],
            global_related_tests=global_tests[:50],
            global_recommended_commands=self._commands_for_tests(global_tests)[:5],
            confidence="medium" if impacts else "unknown",
            warnings=list(dict.fromkeys(list(pkg.warnings or []) + list(verify.warnings or []))),
        )

    def _match(
        self,
        item_targets: list[str],
        changed_files: list[str],
        global_impacted: list[str],
        global_tests: list[str],
    ) -> tuple[list[str], list[str], list[str], str]:
        reasons: list[str] = []
        direct = [path for path in global_impacted if path in item_targets or path in changed_files]
        if direct:
            related = [test for test in global_tests if any(Path(path).stem in test for path in direct)]
            reasons.append("exact_path_match")
            return direct[:30], (related or global_tests)[:15], reasons, "high" if related else "medium"
        basenames = {Path(target).name for target in item_targets}
        by_base = [path for path in global_impacted if Path(path).name in basenames]
        if by_base:
            related = [test for test in global_tests if any(Path(path).stem in test for path in by_base)]
            reasons.append("basename_match")
            return by_base[:30], (related or global_tests)[:15], reasons, "medium"
        top_dirs = {path.split("/")[0] for path in item_targets if "/" in path}
        by_module = [path for path in global_impacted if path.split("/")[0] in top_dirs]
        if by_module:
            related = [test for test in global_tests if any(directory in test for directory in top_dirs)]
            reasons.append("module_dir_match")
            return by_module[:30], (related or global_tests)[:15], reasons, "medium"
        reasons.append("global_fallback")
        return global_impacted[:30], global_tests[:15], reasons, "low" if (global_impacted or global_tests) else "unknown"

    def _commands_for_tests(self, tests: list[str]) -> list[str]:
        py_tests = [test for test in tests if test.endswith(".py")][:5]
        js_tests = [
            test
            for test in tests
            if any(test.endswith(suffix) for suffix in [".test.js", ".spec.js", ".test.ts", ".spec.ts"])
        ][:5]
        out = []
        if py_tests:
            out.append("pytest " + " ".join(py_tests))
        if js_tests:
            out.append("npm test -- " + " ".join(js_tests))
        return out[:5]
