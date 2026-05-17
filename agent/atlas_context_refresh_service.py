from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_context_local_collectors import collect_code_intel_context, collect_git_context
from agent.atlas_context_nexus_adapter import AtlasContextNexusAdapter
from agent.atlas_context_refresh_policies import get_context_refresh_policy
from agent.atlas_context_refresh_schema import AtlasContextBundle, AtlasContextRefreshRequest, AtlasContextSource
from agent.atlas_journal import AtlasJournal


class AtlasContextRefreshService:
    def __init__(self, journal: AtlasJournal | None = None, nexus_adapter: AtlasContextNexusAdapter | None = None):
        self.journal = journal
        self.nexus_adapter = nexus_adapter or AtlasContextNexusAdapter()

    def refresh(self, request: AtlasContextRefreshRequest) -> AtlasContextBundle:
        policy = get_context_refresh_policy(request.policy_id)
        bundle_id = f"ctx_{uuid4().hex[:10]}"
        warnings: list[str] = []
        errors: list[str] = []
        sources: list[AtlasContextSource] = []
        changed_files = list(dict.fromkeys(request.changed_files))[: policy.max_changed_files]
        if len(request.changed_files) > policy.max_changed_files:
            warnings.append("changed_files_truncated")

        if request.include_local_tools and policy.allow_local_dev_tools and request.project_path:
            local = collect_git_context(request.project_path, changed_files, {"max_changed_files": policy.max_changed_files})
            sources.append(AtlasContextSource(source_id="git_status", source_type="git_status", title="Git status", summary="Collected git status."))
            for d in local["diffs"]:
                sources.append(AtlasContextSource(source_id=f"git_diff:{d.relative_path}", source_type="git_diff", title=f"Git diff {d.relative_path}", summary=(d.diff[:300] or "No diff"), path=d.relative_path))
            sources.append(AtlasContextSource(source_id="project_tree", source_type="project_tree", title="Project tree", summary=f"{len(local['tree'].tree)} files sampled."))
            for o in local["outlines"]:
                sources.append(AtlasContextSource(source_id=f"outline:{o.relative_path}", source_type="file_outline", title=f"Outline {o.relative_path}", summary="; ".join(o.outline[:8]), path=o.relative_path))

        if policy.allow_code_intel and request.project_path:
            intel = collect_code_intel_context(request.project_path, changed_files, {})
            sources.append(AtlasContextSource(source_id="symbol_index", source_type="symbol_index", title="Symbol index", summary=f"{len(intel['symbol_index'].symbols)} symbols."))
            sources.append(AtlasContextSource(source_id="dependency_graph", source_type="dependency_graph", title="Dependency graph", summary=f"{len(intel['dependency_graph'].edges)} edges."))
            sources.append(AtlasContextSource(source_id="related_tests", source_type="related_tests", title="Related tests", summary=f"{len(intel['related_tests'].related_tests)} tests."))
            related_tests = intel["related_tests"].related_tests
            dependency_edges = [e.model_dump() for e in intel["dependency_graph"].edges[:100]]
        else:
            related_tests = []
            dependency_edges = []

        if policy.allow_nexus_local_knowledge:
            _src, w = self.nexus_adapter.search_local(request.query, policy.max_sources)
            warnings.extend(w)

        if request.include_nexus_search:
            if not policy.allow_nexus_web_search:
                warnings.append("web_search_not_allowed")
            elif request.trigger != "manual":
                warnings.append("web_search_requires_manual_trigger")
            else:
                _src, w = self.nexus_adapter.search_web(request.query, policy.max_sources)
                warnings.extend(w)

        if request.include_deep_research:
            if not policy.allow_deep_research:
                warnings.append("deep_research_not_allowed")
            elif request.trigger != "manual":
                warnings.append("deep_research_requires_manual_trigger")
            else:
                _src, w = self.nexus_adapter.start_deep_research(request.query, {"max_sources": policy.max_sources})
                warnings.extend(w)

        sources = sources[: min(policy.max_sources, request.max_sources)]
        context_text = self._build_context_text(request, policy.policy_id, changed_files, sources, warnings)
        max_chars = min(policy.max_context_chars, request.max_context_chars)
        if len(context_text) > max_chars:
            context_text = context_text[:max_chars]
            warnings.append("truncated")

        status = "ready" if not warnings else "partial"
        if "web_search_not_allowed" in warnings or "deep_research_not_allowed" in warnings:
            status = "blocked"
        bundle = AtlasContextBundle(bundle_id=bundle_id, pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, trigger=request.trigger, policy_id=policy.policy_id, status=status, query=request.query, context_text=context_text, sources=sources, changed_files=changed_files, related_tests=related_tests, dependency_edges=dependency_edges, warnings=warnings, errors=errors, metadata={"workspace_id": request.workspace_id}, created_at=datetime.now(timezone.utc).isoformat())
        self._save_bundle(bundle)
        return bundle

    def _save_bundle(self, bundle: AtlasContextBundle) -> None:
        root = Path("ca_data") / "atlas" / "context_bundles" / bundle.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{bundle.bundle_id}.json").write_text(json.dumps(bundle.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (root / f"{bundle.bundle_id}.md").write_text(bundle.context_text, encoding="utf-8")

    def _build_context_text(self, request: AtlasContextRefreshRequest, policy_id: str, changed_files: list[str], sources: list[AtlasContextSource], warnings: list[str]) -> str:
        lines = ["# Context Refresh Bundle", "", "## Trigger", f"- trigger: {request.trigger}", f"- policy: {policy_id}", f"- item_id: {request.item_id}", f"- changed_files: {', '.join(changed_files)}", "", "## Sources"]
        lines.extend([f"- [{s.source_type}] {s.title}: {s.summary}" for s in sources])
        lines.append("")
        lines.append("## Warnings")
        lines.extend([f"- {w}" for w in warnings] or ["- none"])
        return "\n".join(lines)
