from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_verification_planning_schema import AtlasVerificationPlanningRequest, AtlasVerificationPlan, AtlasCITestSelectionHint, AtlasVerificationPlanItemHint


class _RepoContextPackageBuilder(Protocol):
    def build_package(self, req: AtlasRepoContextRequest):
        ...


class _UnavailableRepoContextPackager:
    status = "missing"
    related_tests: list[str] = []
    impacted_files: list[str] = []
    warnings = ["repo_context_packager_unavailable_non_blocking"]
    confidence = "unknown"

    def build_package(self, req: AtlasRepoContextRequest):
        return self


class AtlasVerificationPlanningService:
    def __init__(self, *, data_root, packager: _RepoContextPackageBuilder | None = None):
        self.data_root = Path(data_root)
        self.packager = packager or _UnavailableRepoContextPackager()

    def build_plan(self, req: AtlasVerificationPlanningRequest) -> AtlasVerificationPlan:
        repo_req = AtlasRepoContextRequest(
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            goal=req.goal,
            changed_files=list(req.changed_files),
            target_files=list(req.target_files),
            allow_build_if_missing=False,
            mode="scope_summary",
        )
        pkg = self.packager.build_package(repo_req)
        status = pkg.status if pkg.status in {"available", "partial", "missing"} else "missing"
        related_tests = list(pkg.related_tests)[:30]
        cmds = []
        py = [t for t in related_tests if t.endswith('.py')]
        js = [t for t in related_tests if any(t.endswith(s) for s in ['.test.js','.spec.js','.test.ts','.spec.ts'])]
        if py:
            cmds.append("pytest " + " ".join(py[:5]))
        if js:
            cmds.append("npm test -- " + " ".join(js[:5]))
        ci_hints = [
            AtlasCITestSelectionHint(label="python-tests", reason="python related tests detected", metadata={"count": len(py)}),
            AtlasCITestSelectionHint(label="js-tests", reason="js/ts related tests detected", metadata={"count": len(js)}),
        ]
        ci_hints = [h for h in ci_hints if h.metadata.get("count", 0) > 0][:5]
        impacted = list(pkg.impacted_files)[:100]
        per_item = [AtlasVerificationPlanItemHint(item_id="global", related_tests=related_tests[:10], recommended_commands=cmds[:5], manual_steps=["Review impacted files manually.", "Run suggested tests manually.", "Check CI jobs manually."], ci_hints=ci_hints[:5], metadata={"advisory_only": True, "executed": False})]
        warnings = list(pkg.warnings)
        if status != "available":
            warnings.append("repo_index_missing_or_partial_non_blocking")
        return AtlasVerificationPlan(status=status, workspace_id=req.workspace_id, project_path=req.project_path, goal=req.goal, changed_files=list(req.changed_files), target_files=list(req.target_files), impacted_files=impacted, related_tests=related_tests, recommended_commands=cmds[:5], manual_verification_steps=["Review impacted files manually.", "Run suggested tests manually.", "Check CI jobs manually."][:5], ci_selection_hints=ci_hints, per_item_hints=per_item, confidence=pkg.confidence, warnings=list(dict.fromkeys(warnings)), metadata={"advisory_only": True, "commands_are_suggestions_only": True, "executed": False, "shell_executed": False, "remote_git_executed": False, "auto_verification_triggered": False, "auto_test_execution_triggered": False, "no_auto_build": True, "no_execution": True})
