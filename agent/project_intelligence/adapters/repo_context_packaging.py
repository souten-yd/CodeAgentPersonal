"""Project Intelligence repository-context packaging helper.

This retained helper replaces the retired legacy ``AtlasRepoContextPlannerPackager``
owner while preserving the same advisory, non-executing schema contract.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from agent.atlas_repo_context_planner_schema import (
    AtlasImpactedTestRecommendation,
    AtlasRepoContextPlannerPackage,
)
from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.project_intelligence.adapters.repo_context_service import ProjectIntelligenceRepoContextService


class ProjectIntelligenceRepoContextPackager:
    """Build bounded advisory planner context from repository-context summaries."""

    def __init__(self, *, data_root, repo_context_service=None, journal=None):
        self.data_root = Path(data_root)
        self.repo_context_service = repo_context_service or ProjectIntelligenceRepoContextService(data_root=self.data_root)
        self.journal = journal

    def _safe_summary(self, request: AtlasRepoContextRequest):
        try:
            return self.repo_context_service.build_plan_scope_summary(request)
        except Exception:
            return type(
                "UnavailableRepoContextSummary",
                (),
                {
                    "status": "missing",
                    "changed_files": request.changed_files,
                    "target_files": request.target_files,
                    "related_tests": [],
                    "confidence": "unknown",
                    "impacted_files": [],
                    "likely_modules": [],
                    "risk_notes": [],
                    "repo_index_snapshot": {},
                },
            )()

    def build_package(self, request: AtlasRepoContextRequest) -> AtlasRepoContextPlannerPackage:
        meta = {
            "generated_for": "planner_prompt_packaging",
            "no_auto_build": True,
            "no_execution": True,
            "full_graph_included": False,
            "full_source_included": False,
        }
        summary = self._safe_summary(request)
        if summary.status != "available":
            return AtlasRepoContextPlannerPackage(
                status=summary.status,
                package_id=f"repopkg_{uuid4().hex[:12]}",
                workspace_id=request.workspace_id,
                project_path=request.project_path,
                goal=request.goal,
                changed_files=request.changed_files,
                target_files=request.target_files,
                planner_context_text=(
                    f"Repo Context status: {summary.status}. "
                    "Advisory only; proceed without repo index context."
                )[:6000],
                confidence="unknown",
                warnings=["repo_context_unavailable"],
                metadata=meta,
            )

        snapshot = summary.repo_index_snapshot if isinstance(summary.repo_index_snapshot, dict) else {}
        impacted_files = list(summary.impacted_files)[:50]
        related_tests = list(summary.related_tests)[:30]
        text = "\n".join(
            [
                "# Repo Context Summary",
                f"- index_run_id: {snapshot.get('index_run_id', '')}",
                f"- confidence: {summary.confidence}",
                f"- target_files: {', '.join(summary.target_files[:10])}",
                f"- impacted_files: {', '.join(impacted_files[:12])}",
                f"- related_tests: {', '.join(related_tests[:10])}",
                "Guidance:",
                "- Treat this as advisory context.",
                "- Do not assume unlisted files are unaffected.",
                "- Prefer small, scoped plan items.",
                "- Include verification suggestions, but do not execute tests automatically.",
            ]
        )
        rec = self.build_impacted_test_recommendation(request)
        return AtlasRepoContextPlannerPackage(
            status="available",
            package_id=f"repopkg_{uuid4().hex[:12]}",
            workspace_id=request.workspace_id,
            project_path=request.project_path,
            project_hash=str(snapshot.get("project_hash", "")),
            index_run_id=str(snapshot.get("index_run_id", "")),
            goal=request.goal,
            changed_files=list(summary.changed_files),
            target_files=list(summary.target_files),
            impacted_files=impacted_files,
            related_tests=related_tests,
            impacted_symbols=list(snapshot.get("impacted_symbols", []))[:50],
            likely_modules=list(summary.likely_modules)[:30],
            route_hints=list((snapshot.get("route_summary") or {}).keys())[:30],
            ui_event_hints=list((snapshot.get("ui_event_summary") or {}).keys())[:30],
            risk_notes=list(summary.risk_notes)[:20],
            confidence=summary.confidence,
            planner_context_text=text[:6000],
            recommended_test_plan={
                "related_tests": rec.related_tests,
                "recommended_commands": rec.recommended_commands,
                "confidence": rec.confidence,
            },
            warnings=list(snapshot.get("warnings", []))[:10],
            errors=list(snapshot.get("errors", []))[:10],
            metadata=meta,
        )

    def build_impacted_test_recommendation(
        self, request: AtlasRepoContextRequest
    ) -> AtlasImpactedTestRecommendation:
        summary = self._safe_summary(request)
        related_tests = list(summary.related_tests)[:30]
        commands = []
        py_tests = [test for test in related_tests if test.endswith(".py")]
        js_tests = [
            test
            for test in related_tests
            if any(test.endswith(suffix) for suffix in [".test.js", ".spec.ts", ".spec.js", ".test.ts"])
        ]
        if py_tests:
            commands.append("pytest " + " ".join(py_tests[:5]))
        if js_tests:
            commands.append("npm test -- " + " ".join(js_tests[:5]))
        return AtlasImpactedTestRecommendation(
            status=summary.status if summary.status in {"available", "missing", "partial"} else "missing",
            changed_files=list(summary.changed_files),
            target_files=list(summary.target_files),
            related_tests=related_tests,
            recommended_commands=commands[:5],
            test_selection_reason={"source": "repo_context.related_tests", "status": summary.status},
            confidence=summary.confidence,
            warnings=[] if summary.status == "available" else ["repo_context_unavailable"],
            metadata={
                "commands_are_suggestions_only": True,
                "executed": False,
                "shell_executed": False,
                "remote_git_executed": False,
            },
        )
