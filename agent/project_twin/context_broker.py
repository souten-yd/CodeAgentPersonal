"""Phase-aware Context Broker (PDT-5).

Selects a bounded, evidence-backed twin slice for an Atlas phase. The broker is the only
component that reads the store here; consumers receive a `TwinContextSlice` through the
`TwinContextPort` and never touch private storage.

Guarantees:
- stays within the requested token budget for non-essential items;
- never drops essential safety/requirement items (they are included first; if they alone
  exceed budget the slice is marked truncated and the overflow is reported, but essentials
  are kept — safety over budget);
- records an inclusion reason per item and an exclusion list with reasons;
- when disabled (feature flag off) returns an empty slice so current Atlas behavior is
  preserved unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.project_twin.contracts import (
    ContextItem,
    TwinContextRequest,
    TwinContextSlice,
    TwinQuery,
)
from agent.project_twin.types import HISTORICAL_STATUSES

# twin node_type -> slice category
_CATEGORY = {
    "requirement": "requirements",
    "constraint": "requirements",
    "class": "symbols",
    "function": "symbols",
    "method": "symbols",
    "module": "symbols",
    "file": "symbols",
    "api_route": "symbols",
    "test": "tests",
    "fixture": "tests",
    "evidence": "observations",
    "verification": "observations",
    "event_handler": "side_effects",
    "nexus_evidence": "nexus_evidence",
    "nexus_document": "nexus_evidence",
    "nexus_report": "nexus_evidence",
    "incident": "incidents",
    "risk": "incidents",
}

_ESSENTIAL_CATEGORIES = {"requirements", "preserve_behaviors"}

# phase -> categories that get a relevance boost
_PHASE_BOOST = {
    "requirement_analysis": {"requirements"},
    "project_investigation": {"symbols", "side_effects"},
    "planning": {"requirements", "symbols", "tests"},
    "generation": {"symbols", "tests"},
    "review": {"symbols", "side_effects", "tests"},
    "verification": {"tests", "observations"},
    "repair": {"symbols", "observations", "tests"},
    "final_rollup": {"requirements", "observations"},
}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4 + 2)


class TwinContextBroker:
    def __init__(self, store, *, enabled: bool = True, candidate_limit: int = 1000, skill_resolver=None) -> None:
        self._store = store
        self._enabled = enabled
        self._candidate_limit = candidate_limit
        self._skill_resolver = skill_resolver

    @property
    def enabled(self) -> bool:
        return self._enabled

    def build_slice(self, request: TwinContextRequest) -> TwinContextSlice:
        now = datetime.now(timezone.utc)
        head = self._store.get_health(request.project_id).twin_revision_id

        if not self._enabled:
            return TwinContextSlice(
                project_id=request.project_id,
                twin_revision_id=head,
                phase=request.phase,
                used_tokens=0,
                excluded=[{"reason": "broker_disabled"}],
                truncated=False,
            )

        target_set = set(request.target_refs)
        boost_categories = _PHASE_BOOST.get(request.phase, set())

        result = self._store.query(
            TwinQuery(project_id=request.project_id, limit=self._candidate_limit, min_confidence=request.min_confidence)
        )

        scored: list[tuple[float, str, ContextItem]] = []
        uncertainties: list[ContextItem] = []
        for node in result.nodes:
            category = _CATEGORY.get(node.node_type, "symbols")
            is_target = node.canonical_ref in target_set
            reasons = []
            if is_target:
                reasons.append("target_ref")
            if category in boost_categories:
                reasons.append(f"phase:{request.phase}")
            if not reasons:
                reasons.append("project_context")

            item = ContextItem(
                item_type=node.node_type,
                canonical_ref=node.canonical_ref,
                summary=f"{node.label} [{node.node_type}]",
                status=node.status,
                confidence=node.confidence,
                source_refs=[node.source_ref],
                evidence_refs=node.evidence_refs,
                inclusion_reason=", ".join(reasons),
                estimated_tokens=estimate_tokens(node.label) + 6,
            )

            score = node.confidence
            if is_target:
                score += 1.0
            if category in boost_categories:
                score += 0.5
            scored.append((score, category, item))

        # Contradicted/invalidated facts surface as uncertainties when requested.
        if request.include_contradictions:
            hist = self._store.query(
                TwinQuery(project_id=request.project_id, statuses=["contradicted", "invalidated"], limit=50)
            )
            for node in hist.nodes:
                if node.status in HISTORICAL_STATUSES:
                    uncertainties.append(
                        ContextItem(
                            item_type=node.node_type, canonical_ref=node.canonical_ref,
                            summary=f"{node.label} ({node.status})", status=node.status,
                            confidence=node.confidence, source_refs=[node.source_ref],
                            evidence_refs=node.evidence_refs, inclusion_reason="contradiction_history",
                            estimated_tokens=estimate_tokens(node.label) + 4,
                        )
                    )

        scored.sort(key=lambda t: t[0], reverse=True)

        slice_ = TwinContextSlice(
            project_id=request.project_id, twin_revision_id=head, phase=request.phase,
            uncertainties=uncertainties,
        )
        used = 0
        excluded: list[dict] = []
        truncated = False

        # Pass 1: essentials (requirements / preserve_behaviors) — always included.
        essentials = [(c, it) for _, c, it in scored if c in _ESSENTIAL_CATEGORIES]
        non_essentials = [(s, c, it) for s, c, it in scored if c not in _ESSENTIAL_CATEGORIES]

        for category, item in essentials:
            getattr(slice_, category).append(item)
            used += item.estimated_tokens
        if used > request.token_budget:
            truncated = True
            excluded.append({"reason": "essentials_exceed_budget", "used_tokens": used, "budget": request.token_budget})

        # Pass 2: non-essentials by score until the budget is exhausted.
        for _, category, item in non_essentials:
            if used + item.estimated_tokens > request.token_budget:
                truncated = True
                excluded.append({"reason": "token_budget", "canonical_ref": item.canonical_ref})
                continue
            getattr(slice_, category).append(item)
            used += item.estimated_tokens

        # Optional skill items (advisory only; never authority). Fit into remaining budget.
        if self._skill_resolver is not None:
            from agent.project_twin.contracts import SkillResolutionRequest

            resolved = self._skill_resolver.resolve(
                SkillResolutionRequest(
                    project_id=request.project_id, objective=request.objective,
                    phase=request.phase, target_refs=request.target_refs, limit=5,
                )
            )
            for item in resolved.skills:
                if used + item.estimated_tokens > request.token_budget:
                    truncated = True
                    excluded.append({"reason": "token_budget", "canonical_ref": item.canonical_ref})
                    continue
                slice_.skills.append(item)
                used += item.estimated_tokens

        slice_.used_tokens = used
        slice_.excluded = excluded
        slice_.truncated = truncated
        return slice_
