"""Plan-time Nexus web-research decision + bounded execution (PIBIH-5).

Atlas already has a gated web-research *bridge* (``AtlasNexusWebResearchClient`` ->
``AtlasNexusResearchAdapter``), but planning never decided *whether* live web research was useful
and never reflected it in the plan. This module adds that decision point:

- ``should_research`` decides eligibility from the requirement text (external API/library/framework
  references, UI/browser/platform terms, greenfield/feature signals) and user preference;
- ``AtlasPlanTimeResearchService.research`` runs a *bounded* research job only when research is both
  eligible AND globally enabled (``ATLAS_NEXUS_WEB_RESEARCH=1``), and otherwise returns a truthful
  skipped result with a warning. It never raises and never fabricates external evidence.

External web research stays OFF by default and policy-gated; the result is always advisory context,
never authoritative proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.atlas_nexus_research_adapter import AtlasNexusResearchAdapter
from agent.atlas_nexus_research_schema import AtlasNexusResearchRequest
from agent.atlas_nexus_web_research_client import AtlasNexusWebResearchClient, web_research_enabled

# Lowercased substrings that signal external knowledge could help planning.
_EXTERNAL_TERMS = (
    "api", "sdk", "library", "framework", "package", "dependency", "protocol", "oauth", "webhook",
    "integrate", "integration", "third-party", "third party", "best practice", "convention", "spec",
    "standard", "rfc", "schema", "driver", "plugin", "migration",
)
_PLATFORM_TERMS = (
    "browser", "safari", "chrome", "firefox", "edge", "ios", "android", "mobile", "css", "html",
    "react", "vue", "svelte", "angular", "tailwind", "webgl", "canvas", "websocket", "platform",
    "compatibility", "polyfill",
)
_FEATURE_TERMS = (
    "greenfield", "from scratch", "new feature", "add support", "implement support", "brand new",
)


def should_research(requirement_text: str, *, use_nexus: bool = True, force: bool = False) -> tuple[bool, str]:
    """Return ``(eligible, reason)`` for plan-time web research.

    A purely-internal refactor/rename with no external signal is ineligible; anything referencing an
    external API/library/framework, a browser/platform concern, or a greenfield feature is eligible.
    """
    if force:
        return True, "forced"
    if not use_nexus:
        return False, "nexus_disabled_by_request"
    text = " ".join(str(requirement_text or "").lower().split())
    if not text:
        return False, "empty_requirement"
    for kw in _EXTERNAL_TERMS:
        if kw in text:
            return True, f"external_signal:{kw}"
    for kw in _PLATFORM_TERMS:
        if kw in text:
            return True, f"platform_signal:{kw}"
    for kw in _FEATURE_TERMS:
        if kw in text:
            return True, f"feature_signal:{kw}"
    return False, "no_external_signal"


@dataclass
class PlanTimeResearchResult:
    eligible: bool
    called: bool
    reason: str
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    context_pack_id: str = ""
    status: str = "skipped"
    warnings: list[str] = field(default_factory=list)
    advisory: bool = True  # always advisory context, never authoritative proof

    def to_metadata(self) -> dict[str, Any]:
        """Compact advisory section for PlanPool/PlanItem metadata."""
        return {
            "enabled": web_research_enabled(),
            "eligible": self.eligible,
            "called": self.called,
            "reason": self.reason,
            "status": self.status,
            "advisory": True,
            "summary": self.summary,
            "findings": self.findings[:8],
            "sources": self.sources[:8],
            "context_pack_id": self.context_pack_id,
            "warnings": list(self.warnings),
        }


class AtlasPlanTimeResearchService:
    def __init__(
        self,
        *,
        adapter: AtlasNexusResearchAdapter | None = None,
        client: object | None = None,
        max_sources: int = 6,
    ) -> None:
        self._adapter = adapter
        self._client = client
        self._max_sources = max_sources

    def research(
        self,
        *,
        requirement_text: str,
        pool_id: str = "",
        item_id: str = "",
        run_id: str = "",
        project_id: str = "atlas",
        use_nexus: bool = True,
        force: bool = False,
    ) -> PlanTimeResearchResult:
        eligible, reason = should_research(requirement_text, use_nexus=use_nexus, force=force)
        if not eligible:
            return PlanTimeResearchResult(eligible=False, called=False, reason=reason, status="skipped", warnings=[reason])
        if not web_research_enabled():
            # Eligible, but external web research is globally off: never call out, never fabricate
            # evidence — record a truthful warning so the plan reflects that research was skipped.
            return PlanTimeResearchResult(
                eligible=True, called=False, reason="eligible_but_web_research_disabled",
                status="skipped", warnings=["web_research_disabled"],
            )
        adapter = self._adapter or AtlasNexusResearchAdapter(
            nexus_client=self._client or AtlasNexusWebResearchClient(max_sources=self._max_sources)
        )
        request = AtlasNexusResearchRequest(
            pool_id=pool_id, item_id=item_id, run_id=run_id, source="planner",
            purpose="web_research", query=str(requirement_text or "").strip()[:500],
            project_name=project_id, allow_web=True, max_sources=self._max_sources,
            metadata={"project_id": project_id, "plan_time": True},
        )
        try:
            pack = adapter.run_research(request)
        except Exception as exc:  # noqa: BLE001 - research must never fail planning.
            return PlanTimeResearchResult(
                eligible=True, called=True, reason="research_error", status="completed_with_warnings",
                warnings=[f"plan_time_research_failed:{str(exc)[:160]}"],
            )
        findings = [
            {"title": f.title, "content": (f.content or "")[:300], "type": f.finding_type}
            for f in pack.findings[:8]
        ]
        return PlanTimeResearchResult(
            eligible=True, called=True, reason="researched",
            summary=pack.summary, findings=findings, sources=list(pack.sources[:8]),
            context_pack_id=pack.context_pack_id, status=str(pack.status),
            warnings=list(pack.warnings), advisory=True,
        )
