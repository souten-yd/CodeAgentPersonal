"""Golden Patch Retrieval (TFG-10 / Package 9A).

Retrieve prior *successful* patches as advisory examples for a new task, keyed by task
category, Forge route, model, affected refs, gate findings, and proof outcome.

This is an evidence-backed optional accelerator, NOT a P0 acceptance gate:

- only accepted (proof-passed) patches are indexed;
- retrieval is similarity-ranked and thresholded; an unrelated patch is not returned;
- results are advisory examples only — they never override Project Twin, Contract
  Sentinel, StateMirror, Schema Guardian, or TwinProof findings;
- retrieval can be disabled (``enabled=False``) without changing any correctness path,
  because nothing downstream depends on a match being present.
"""
from __future__ import annotations

from pydantic import Field

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel

# Similarity weights (sum to 1.0). Affected-ref overlap and task category dominate.
_W_TASK = 0.35
_W_AFFECTED = 0.30
_W_ROUTE = 0.20
_W_MODEL = 0.15

DEFAULT_RETRIEVAL_THRESHOLD = 0.5


class GoldenPatch(ForgeModel):
    """An indexed record of a patch that passed its proof gates. The patch body itself
    is referenced, never inlined, so the index stays advisory and data-free."""

    schema_version: str = FORGE_SCHEMA_VERSION
    patch_id: str = Field(min_length=1)
    task_category: str = ""
    route: ForgeRoute | None = None
    model_id: str = ""
    provider_id: str = ""
    affected_refs: list[str] = Field(default_factory=list)
    gate_refs: list[str] = Field(default_factory=list)
    # Only "accepted" outcomes are eligible for the index.
    proof_outcome: str = "accepted"
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class RetrievalQuery(ForgeModel):
    task_category: str = ""
    route: ForgeRoute | None = None
    model_id: str = ""
    affected_refs: list[str] = Field(default_factory=list)


class RetrievedPatch(ForgeModel):
    patch: GoldenPatch
    confidence: float
    # Always advisory: retrieved patches are examples, never authority.
    advisory: bool = True
    match_reasons: list[str] = Field(default_factory=list)


def _ref_overlap(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _score(query: RetrievalQuery, patch: GoldenPatch) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    if query.task_category and query.task_category == patch.task_category:
        score += _W_TASK
        reasons.append("task_category")
    if query.route is not None and query.route == patch.route:
        score += _W_ROUTE
        reasons.append("route")
    if query.model_id and query.model_id == patch.model_id:
        score += _W_MODEL
        reasons.append("model")
    overlap = _ref_overlap(query.affected_refs, patch.affected_refs)
    if overlap > 0:
        score += _W_AFFECTED * overlap
        reasons.append(f"affected_refs={round(overlap, 2)}")
    return round(score, 4), reasons


class GoldenPatchIndex:
    """In-memory advisory index of successful patches. Only accepted patches are kept."""

    def __init__(self) -> None:
        self._patches: dict[str, GoldenPatch] = {}

    def index_patch(self, patch: GoldenPatch) -> bool:
        """Index an accepted patch. Returns False (and indexes nothing) for any
        non-accepted outcome — failures are never offered as golden examples."""
        if patch.proof_outcome != "accepted":
            return False
        self._patches[patch.patch_id] = patch
        return True

    def __len__(self) -> int:
        return len(self._patches)

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        enabled: bool = True,
        threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
        limit: int = 5,
    ) -> list[RetrievedPatch]:
        """Return advisory patch matches at or above the threshold, best first.

        ``enabled=False`` short-circuits to an empty list so retrieval can be turned off
        with no effect on any correctness path."""
        if not enabled:
            return []
        scored: list[RetrievedPatch] = []
        for patch in self._patches.values():
            confidence, reasons = _score(query, patch)
            if confidence >= threshold:
                scored.append(RetrievedPatch(patch=patch, confidence=confidence, match_reasons=reasons))
        scored.sort(key=lambda r: (r.confidence, r.patch.patch_id), reverse=True)
        return scored[:limit]


__all__ = [
    "DEFAULT_RETRIEVAL_THRESHOLD",
    "GoldenPatch",
    "RetrievalQuery",
    "RetrievedPatch",
    "GoldenPatchIndex",
]
