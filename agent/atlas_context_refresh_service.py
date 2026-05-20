from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_context_local_collectors import collect_code_intel_context, collect_git_context
from agent.atlas_context_nexus_adapter import AtlasContextNexusAdapter
from agent.atlas_context_refresh_policies import get_context_refresh_policy
from agent.atlas_context_refresh_schema import AtlasContextBundle, AtlasContextRefreshRequest, AtlasContextSource
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_repo_context_service import AtlasRepoContextService


class AtlasContextRefreshService:
    def __init__(self, journal: AtlasJournal | None = None, nexus_adapter: AtlasContextNexusAdapter | None = None, data_root: Path | None = None):
        self.journal = journal
        self.nexus_adapter = nexus_adapter or AtlasContextNexusAdapter()
        self.data_root = data_root or Path.cwd()

    def refresh(self, request: AtlasContextRefreshRequest) -> AtlasContextBundle:
        policy = get_context_refresh_policy(request.policy_id)
        bundle_id = f"ctx_{uuid4().hex[:10]}"
        warnings: list[str] = []
        errors: list[str] = []
        sources: list[AtlasContextSource] = []
        max_sources = min(policy.max_sources, request.max_sources)
        max_chars = min(policy.max_context_chars, request.max_context_chars)
        changed_files, changed_files_source, resolve_warnings = self.resolve_changed_files(request, policy.max_changed_files)
        warnings.extend(resolve_warnings)

        self._emit_event("context_refresh_started", request, bundle_id, "ready", 0, warnings, changed_files, 0)

        if request.include_local_tools and policy.allow_local_dev_tools and request.project_path:
            local = collect_git_context(request.project_path, changed_files, {"max_changed_files": policy.max_changed_files})
            warnings.extend(local.get("warnings", []))
            if local.get("status") is not None:
                sources.append(AtlasContextSource(source_id="git_status", source_type="git_status", title="Git status", summary="Collected git status."))
            for d in local.get("diffs", []):
                sources.append(AtlasContextSource(source_id=f"git_diff:{d.relative_path}", source_type="git_diff", title=f"Git diff {d.relative_path}", summary=(d.diff[:300] or "No diff"), path=d.relative_path))
            if local.get("tree") is not None:
                sources.append(AtlasContextSource(source_id="project_tree", source_type="project_tree", title="Project tree", summary=f"{len(local['tree'].tree)} files sampled."))
            for o in local.get("outlines", []):
                sources.append(AtlasContextSource(source_id=f"outline:{o.relative_path}", source_type="file_outline", title=f"Outline {o.relative_path}", summary="; ".join(o.outline[:8]), path=o.relative_path))

        related_tests = []
        dependency_edges = []
        if policy.allow_code_intel and request.project_path:
            intel = collect_code_intel_context(request.project_path, changed_files, {})
            warnings.extend(intel.get("warnings", []))
            if intel.get("symbol_index") is not None:
                sources.append(AtlasContextSource(source_id="symbol_index", source_type="symbol_index", title="Symbol index", summary=f"{len(intel['symbol_index'].symbols)} symbols."))
            if intel.get("dependency_graph") is not None:
                sources.append(AtlasContextSource(source_id="dependency_graph", source_type="dependency_graph", title="Dependency graph", summary=f"{len(intel['dependency_graph'].edges)} edges."))
                dependency_edges = [e.model_dump() for e in intel["dependency_graph"].edges[:100]]
            if intel.get("related_tests") is not None:
                sources.append(AtlasContextSource(source_id="related_tests", source_type="related_tests", title="Related tests", summary=f"{len(intel['related_tests'].related_tests)} tests."))
                related_tests = intel["related_tests"].related_tests

        if policy.allow_nexus_local_knowledge:
            src, w = self.nexus_adapter.search_local(request.query, max_sources)
            sources.extend(src)
            warnings.extend(w)

        if request.include_nexus_search:
            if not policy.allow_nexus_web_search:
                warnings.append("web_search_not_allowed")
            elif request.trigger != "manual":
                warnings.append("web_search_requires_manual_trigger")
            else:
                src, w = self.nexus_adapter.search_web(request.query, max_sources)
                sources.extend(src)
                warnings.extend(w)

        if request.include_deep_research:
            if not policy.allow_deep_research:
                warnings.append("deep_research_not_allowed")
            elif request.trigger != "manual":
                warnings.append("deep_research_requires_manual_trigger")
            else:
                src, w = self.nexus_adapter.start_deep_research(request.query, {"max_sources": max_sources})
                sources.extend(src)
                warnings.extend(w)

        before_truncation = len(sources)
        sources = sources[:max_sources]
        context_text = self._build_context_text(request, policy.policy_id, changed_files, sources, warnings)
        if not isinstance(context_text, str):
            errors.append("context_text_generation_failed")
            status = "failed"
            context_text = ""
        else:
            if len(context_text) > max_chars:
                context_text = context_text[:max_chars]
                warnings.append("truncated")

            status = "ready"
            if "web_search_not_allowed" in warnings or "deep_research_not_allowed" in warnings:
                status = "blocked"
            elif errors:
                status = "failed"
            elif warnings:
                status = "partial"

        bundle = AtlasContextBundle(
            bundle_id=bundle_id,
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id,
            trigger=request.trigger,
            policy_id=policy.policy_id,
            status=status,
            query=request.query,
            context_text=context_text,
            sources=sources,
            changed_files=changed_files,
            related_tests=related_tests,
            dependency_edges=dependency_edges,
            warnings=warnings,
            errors=errors,
            metadata={
                "workspace_id": request.workspace_id,
                "max_sources": max_sources,
                "max_context_chars": max_chars,
                "source_count_before_truncation": before_truncation,
                "source_count_after_truncation": len(sources),
                "context_chars": len(context_text),
                "truncated": "truncated" in warnings,
                "policy_limits": {"max_sources": policy.max_sources, "max_context_chars": policy.max_context_chars, "max_changed_files": policy.max_changed_files},
                "local_collectors_used": ["git_status", "git_diff", "project_tree", "file_outline", "symbol_index", "dependency_graph", "related_tests"],
                "nexus_sources_used": sorted({s.source_type for s in sources if s.source_type in {"nexus_local", "nexus_web", "nexus_deep_research"}}),
                "changed_files_resolution_source": changed_files_source,
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            snapshot = AtlasRepoContextService(data_root=self.data_root).build_snapshot(
                AtlasRepoContextRequest(
                    workspace_id=request.workspace_id,
                    project_path=request.project_path,
                    changed_files=changed_files,
                    target_files=request.target_files,
                    mode="scope_summary",
                    allow_build_if_missing=False,
                )
            )
            bundle.metadata["repo_context_snapshot"] = snapshot.model_dump()
            lines = [
                "",
                "## Repo Context",
                f"- status: {snapshot.status}",
                f"- index_run_id: {snapshot.index_run_id}",
                f"- impacted_files: {', '.join(snapshot.impacted_files[:8])}",
                f"- related_tests: {', '.join(snapshot.related_tests[:8])}",
            ]
            if snapshot.warnings:
                lines.append(f"- warnings: {', '.join(snapshot.warnings[:8])}")
            bundle.context_text = f"{bundle.context_text}\n" + "\n".join(lines)
        except Exception:
            bundle.metadata["repo_context_snapshot"] = {"status": "failed_internal"}
        self._save_bundle(bundle)
        event_name = "context_refresh_completed"
        if status == "partial":
            event_name = "context_refresh_partial"
        elif status == "blocked":
            event_name = "context_refresh_blocked"
        elif status == "failed":
            event_name = "context_refresh_failed"
        self._emit_event(event_name, request, bundle_id, status, len(sources), warnings, changed_files, len(context_text))
        return bundle

    def resolve_changed_files(self, request: AtlasContextRefreshRequest, max_changed_files: int) -> tuple[list[str], str, list[str]]:
        warnings: list[str] = []
        candidates = request.changed_files
        source = "request.changed_files"
        item = None
        if not candidates and self.journal and request.pool_id and request.item_id:
            try:
                pool = self.journal.load_plan_pool(request.pool_id)
            except Exception:
                pool = None
                warnings.append("pool_unavailable")
            if pool is not None:
                item = pool.get_item(request.item_id)
                if item is None:
                    warnings.append("item_unavailable")
        if not candidates and item is not None:
            metadata = item.metadata or {}
            for key, src in [
                ("target_files", "item.metadata.target_files"),
                (("safe_apply", "changed_files"), "item.metadata.safe_apply.changed_files"),
                (("auto_safe_apply", "changed_files"), "item.metadata.auto_safe_apply.changed_files"),
                (("change_snapshot", "target_files"), "item.metadata.change_snapshot.target_files"),
            ]:
                value = metadata.get(key) if isinstance(key, str) else (metadata.get(key[0]) or {}).get(key[1])
                if value:
                    candidates = value
                    source = src
                    break
            if not candidates and item.target_files:
                candidates = item.target_files
                source = "item.target_files"

        cleaned: list[str] = []
        seen: set[str] = set()
        for path in candidates:
            try:
                safe = validate_relative_path(path)
                if not safe:
                    continue
                if safe not in seen:
                    cleaned.append(safe)
                    seen.add(safe)
            except Exception:
                warnings.append(f"invalid_changed_file:{path}")
        if len(cleaned) > max_changed_files:
            cleaned = cleaned[:max_changed_files]
            warnings.append("changed_files_truncated")
        return cleaned, source, warnings

    def _emit_event(self, event_type: str, request: AtlasContextRefreshRequest, bundle_id: str, status: str, source_count: int, warnings: list[str], changed_files: list[str], context_chars: int) -> None:
        if not self.journal or not request.run_id:
            return
        self.journal.append_event(request.pool_id, request.run_id, {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": event_type,
            "metadata": {
                "bundle_id": bundle_id,
                "pool_id": request.pool_id,
                "item_id": request.item_id,
                "trigger": request.trigger,
                "policy_id": request.policy_id,
                "status": status,
                "source_count": source_count,
                "warning_count": len(warnings),
                "changed_files": changed_files,
                "context_chars": context_chars,
            },
        })

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
