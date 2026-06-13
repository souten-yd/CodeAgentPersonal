"""Bridge Atlas planning/generation to the existing Nexus web-research agent.

Nexus already ships a full web research pipeline (`app.nexus.research_agent.run_research_job`:
plan queries -> searxng web search -> download/ingest sources -> LLM synthesis). Atlas's
`AtlasNexusResearchAdapter` was wired with ``nexus_client=None`` so none of it reached planning.

This thin client exposes the `run_research(request)` method the adapter expects and maps the
research-job result to the adapter's ``{summary, findings, status, warnings}`` shape. It is the
GENERAL injection path: useful for greenfield AND for modifying existing code that ADDS a feature
(research how to implement it / conventions), not only new projects.

It is gated OFF by default (``ATLAS_NEXUS_WEB_RESEARCH=1`` to enable) because web research is an
EXTERNAL, policy-gated, minutes-long operation; Local-Only / disabled deployments must not call it.
"""
from __future__ import annotations

import os
from typing import Any


def web_research_enabled() -> bool:
    return str(os.environ.get("ATLAS_NEXUS_WEB_RESEARCH", "") or "").strip() in {"1", "true", "yes", "on"}


class AtlasNexusWebResearchClient:
    """Adapter-facing client backed by app.nexus.research_agent.run_research_job."""

    def __init__(self, *, mode: str = "standard", depth: str = "shallow", max_sources: int = 8, max_downloads: int = 4):
        self.mode = mode
        self.depth = depth
        self.max_sources = max_sources
        self.max_downloads = max_downloads

    def run_research(self, request: Any) -> dict[str, Any]:
        """Run a bounded web-research job for ``request.query`` and return a normalized payload.

        Never raises: on any failure (web search disabled, searxng unavailable, network) it returns a
        completed-with-warnings payload so planning degrades gracefully to no external context.
        """
        query = str(getattr(request, "query", "") or "").strip()
        if not query:
            return {"status": "completed_with_warnings", "summary": "", "findings": [], "warnings": ["empty_query"]}
        if not web_research_enabled():
            return {"status": "completed_with_warnings", "summary": "", "findings": [], "warnings": ["web_research_disabled"]}
        try:
            from app.nexus.research_agent import ResearchAgentInput, run_research_job
        except Exception as exc:  # noqa: BLE001
            return {"status": "completed_with_warnings", "summary": "", "findings": [], "warnings": [f"nexus_research_import_failed:{str(exc)[:120]}"]}
        try:
            result = run_research_job(ResearchAgentInput(
                query=query,
                project=str(getattr(request, "project_id", "") or "atlas"),
                mode=self.mode,
                depth=self.depth,
                max_sources=self.max_sources,
                max_downloads=self.max_downloads,
            ))
        except Exception as exc:  # noqa: BLE001
            return {"status": "completed_with_warnings", "summary": "", "findings": [], "warnings": [f"nexus_research_failed:{str(exc)[:160]}"]}
        return self._normalize(result)

    def _normalize(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"status": "completed_with_warnings", "summary": "", "findings": [], "warnings": ["nexus_research_no_payload"]}
        answer = result.get("answer") if isinstance(result.get("answer"), dict) else {}
        summary = str(answer.get("answer_markdown") or answer.get("answer") or result.get("summary") or "").strip()
        sources = result.get("sources") if isinstance(result.get("sources"), list) else []
        findings: list[dict[str, Any]] = []
        for s in sources[:12]:
            if not isinstance(s, dict):
                continue
            title = str(s.get("title") or s.get("url") or "").strip()
            url = str(s.get("url") or "").strip()
            snippet = str(s.get("snippet") or s.get("summary") or "").strip()[:300]
            if title or snippet:
                findings.append({"title": title[:200], "url": url, "snippet": snippet})
        status = str(result.get("status") or "completed")
        if status not in {"completed", "completed_with_warnings", "degraded", "failed"}:
            status = "completed"
        warnings: list[str] = []
        if status in {"degraded", "failed"}:
            warnings.append(f"nexus_research_status:{status}")
        return {
            "status": "completed" if status == "completed" else "completed_with_warnings",
            "summary": summary,
            "findings": findings,
            "warnings": warnings,
        }
