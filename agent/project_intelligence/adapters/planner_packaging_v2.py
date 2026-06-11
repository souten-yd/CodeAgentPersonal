"""Project Intelligence planner-packaging v2 adapter.

This is the retained implementation for the planner-packaging v2 API after the
legacy ``agent.atlas_planner_packaging_v2_service`` owner is retired. It keeps the
same schema contract while living behind the Project Intelligence adapter surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_context_refresh_v2_schema import AtlasContextRefreshV2Request
from agent.atlas_context_refresh_v2_service import AtlasContextRefreshV2Service
from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMapRequest
from agent.atlas_plan_item_impact_map_service import AtlasPlanItemImpactMapService
from agent.atlas_planner_packaging_v2_schema import (
    AtlasPlannerPackagingV2Package,
    AtlasPlannerPackagingV2Request,
)
from agent.atlas_repo_context_planner_packager import AtlasRepoContextPlannerPackager
from agent.atlas_repo_context_schema import AtlasRepoContextRequest


def _impact_entry_files(item: dict[str, Any]) -> list[str]:
    files = item.get("impacted_files")
    if files is None:
        files = item.get("impacted_paths")
    return list(files or [])


def _impact_entry_tests(item: dict[str, Any]) -> list[str]:
    return list(item.get("related_tests") or [])


def _dedup(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


class ProjectIntelligencePlannerPackagingV2Adapter:
    """Build advisory planner-packaging context without executing commands."""

    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).resolve()

    def build_package(self, req: AtlasPlannerPackagingV2Request) -> AtlasPlannerPackagingV2Package:
        warnings: list[str] = []
        errors: list[str] = []
        repo = dict(req.repo_context_package or {})
        impact = dict(req.plan_item_impact_map or {})
        refresh = dict(req.context_refresh_v2 or {})

        if not repo and req.include_repo_context and req.project_path:
            try:
                repo = AtlasRepoContextPlannerPackager(data_root=self.data_root).build_package(
                    AtlasRepoContextRequest(
                        workspace_id=req.workspace_id,
                        project_path=req.project_path,
                        goal=req.goal,
                        changed_files=req.changed_files,
                        target_files=req.target_files,
                        allow_build_if_missing=False,
                    )
                ).model_dump()
            except Exception as exc:  # pragma: no cover - tested via monkeypatch
                warnings.append("repo_context_unavailable")
                errors.append(str(exc))

        if not impact and req.include_plan_item_impact_map and req.plan_pool:
            try:
                impact = AtlasPlanItemImpactMapService(data_root=self.data_root).build_map(
                    AtlasPlanItemImpactMapRequest(
                        workspace_id=req.workspace_id,
                        project_path=req.project_path,
                        pool_id=req.pool_id,
                        goal=req.goal,
                        changed_files=req.changed_files,
                        target_files=req.target_files,
                        plan_pool=req.plan_pool,
                    )
                ).model_dump()
            except Exception as exc:  # pragma: no cover - tested via monkeypatch
                warnings.append("plan_item_impact_map_unavailable")
                errors.append(str(exc))

        if not refresh and req.include_context_refresh_v2 and req.plan_pool:
            try:
                refresh = AtlasContextRefreshV2Service(data_root=self.data_root).refresh(
                    AtlasContextRefreshV2Request(
                        workspace_id=req.workspace_id,
                        project_path=req.project_path,
                        pool_id=req.pool_id,
                        goal=req.goal,
                        changed_files=req.changed_files,
                        target_files=req.target_files,
                        plan_pool=req.plan_pool,
                        include_plan_item_impact_map=False,
                    )
                ).model_dump()
            except Exception as exc:  # pragma: no cover - tested via monkeypatch
                warnings.append("context_refresh_v2_unavailable")
                errors.append(str(exc))

        impacted = _dedup(
            list(repo.get("impacted_files") or [])
            + [path for entry in impact.get("impacts", []) for path in _impact_entry_files(entry)]
        )[:80]
        related = _dedup(
            list(repo.get("related_tests") or [])
            + list(refresh.get("related_tests") or [])
            + [test for entry in impact.get("impacts", []) for test in _impact_entry_tests(entry)]
        )[:50]
        commands = _dedup(list(refresh.get("recommended_commands") or []))[:10]
        manual_steps = _dedup(list(refresh.get("manual_verification_steps") or []))[:20]

        planner_context_text = (
            "ADVISORY REPOSITORY CONTEXT - DO NOT EXECUTE\n"
            "This context is advisory only. Suggested commands are manual-only. Preserve human approval. "
            "Do not run shell commands, tests, git operations, safe apply, verification, automatic patch "
            "generation, automatic retry, or remote git.\n"
            f"RepoContext status: {repo.get('status', 'missing')}\n"
            f"ImpactMap status: {impact.get('status', 'missing')}\n"
            f"ContextRefreshV2 status: {refresh.get('status', 'missing')}\n"
            "Impacted files: "
            + ", ".join(impacted[:20])
            + "\nRelated tests: "
            + ", ".join(related[:15])
            + "\nManual verification: "
            + "; ".join(manual_steps[:10])
        )
        status = "available" if any([repo, impact, refresh]) else "missing"
        if warnings:
            status = "partial"

        return AtlasPlannerPackagingV2Package(
            status=status,
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            pool_id=req.pool_id,
            goal=req.goal,
            planner_context_text=planner_context_text[:12000],
            context_sections=[
                {"type": "repo_context", "status": repo.get("status", "missing")},
                {"type": "plan_item_impact_map", "status": impact.get("status", "missing")},
                {"type": "context_refresh_v2", "status": refresh.get("status", "missing")},
                {"type": "verification_hints", "status": "available" if (related or commands or manual_steps) else "missing"},
                {"type": "safety_contract", "status": "enforced"},
            ][:20],
            impacted_files=impacted,
            related_tests=related,
            recommended_commands=commands,
            manual_verification_steps=manual_steps,
            ci_selection_hints=list(refresh.get("ci_selection_hints") or [])[:20],
            evidence=list(refresh.get("evidence") or [])[:80],
            confidence=str(repo.get("confidence") or refresh.get("confidence") or impact.get("confidence") or "unknown"),
            warnings=_dedup(warnings)[:30],
            errors=_dedup(errors)[:20],
        )
