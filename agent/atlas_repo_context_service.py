from __future__ import annotations

from pathlib import Path

from agent.atlas_repo_context_schema import AtlasPlanScopeSummary, AtlasRepoContextRequest, AtlasRepoContextSnapshot
from agent.atlas_repo_index_service import AtlasRepoIndexService
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage


class AtlasRepoContextService:
    def __init__(self, *, data_root, repo_index_service=None, repo_index_storage=None, journal=None):
        self.data_root = Path(data_root)
        self.repo_index_service = repo_index_service or AtlasRepoIndexService(self.data_root)
        self.repo_index_storage = repo_index_storage or AtlasRepoIndexStorage(self.data_root)
        self.journal = journal

    def build_snapshot(self, request: AtlasRepoContextRequest) -> AtlasRepoContextSnapshot:
        if not (request.project_path or "").strip():
            return AtlasRepoContextSnapshot(status="missing", workspace_id=request.workspace_id, warnings=["project_path_missing"])
        latest = self.repo_index_service.load_latest(request.workspace_id, request.project_path)
        if not latest:
            return AtlasRepoContextSnapshot(status="missing", workspace_id=request.workspace_id, project_path=request.project_path, warnings=["repo_index_missing"])
        changed = list(dict.fromkeys([*request.changed_files, *request.target_files]))
        impacted_files = []
        related_tests = []
        related_tests_by_file = {}
        if changed:
            impacts = self.repo_index_service.query_impacts(request.project_path, changed)
            related = self.repo_index_service.query_related_tests(request.project_path, changed)
            impacted_files = list(impacts.get("impacted_files", []))
            related_tests = list(related.get("related_tests", []))
            related_tests_by_file = dict(related.get("by_changed_file", {}))
        else:
            impacted_files = list(latest.get("impacted_files", []))
            related_tests = list(latest.get("related_tests", []))

        impacted_files = impacted_files[: max(1, request.max_impacted_files)]
        related_tests = related_tests[: max(1, request.max_related_tests)]
        reason_by_file = {p: "repo_index_impact" for p in impacted_files[:100]}
        return AtlasRepoContextSnapshot(
            status="available",
            workspace_id=request.workspace_id,
            project_path=request.project_path,
            project_hash=self.repo_index_storage.project_hash(request.project_path),
            index_run_id=str(latest.get("index_run_id", "")),
            index_status=str(latest.get("status", "")),
            changed_files=list(request.changed_files),
            target_files=list(request.target_files),
            impacted_files=impacted_files,
            impacted_symbols=list(latest.get("metadata", {}).get("impacted_symbols", []))[:100],
            related_tests=related_tests,
            related_tests_by_file=related_tests_by_file,
            confidence_by_file={p: "medium" for p in impacted_files[:100]},
            reason_by_file=reason_by_file,
            metadata={"artifact": "latest.json"},
        )

    def build_plan_scope_summary(self, request: AtlasRepoContextRequest) -> AtlasPlanScopeSummary:
        snapshot = self.build_snapshot(request)
        if snapshot.status != "available":
            return AtlasPlanScopeSummary(
                status=snapshot.status,
                scope_source="missing",
                target_files=request.target_files,
                changed_files=request.changed_files,
                confidence="unknown",
                repo_index_snapshot=snapshot.model_dump(),
            )
        likely_modules = sorted({x.split("/", 1)[0] for x in snapshot.impacted_files if "/" in x})[:20]
        confidence = "high" if snapshot.impacted_files else "low"
        return AtlasPlanScopeSummary(
            status="available",
            scope_source="repo_index",
            target_files=snapshot.target_files,
            changed_files=snapshot.changed_files,
            impacted_files=snapshot.impacted_files[:100],
            related_tests=snapshot.related_tests[:50],
            likely_modules=likely_modules,
            risk_notes=[] if confidence == "high" else ["limited_repo_index_signal"],
            confidence=confidence,
            repo_index_snapshot=snapshot.model_dump(),
        )
