"""Twin memory integration (PDT-6).

Integrates the existing `HybridMemoryStore` instead of building a competing memory
subsystem. Durable, provenance-bearing memory facts live in the twin's `learning` domain;
the adapter enforces the verified-promotion policy so unverified model inference can never
become durable memory.

Implements `TwinMemoryPort` (recall / propose_promotion / supersede). The adapter holds
the store and an optional `HybridMemoryStore`; consumers depend on the port.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.project_twin.contracts import (
    ContextItem,
    MemoryPromotionDecision,
    MemoryPromotionRequest,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemorySupersedeRequest,
    TwinDelta,
    TwinEvidence,
    TwinNode,
    TwinQuery,
)
from agent.project_twin.static_graph import nid
from agent.project_twin.types import NON_VERIFIED_DERIVATIONS

_LEARNING = "learning"

# canonical ref scheme -> learning node type
_MEMORY_TYPES = {
    "decision": "architecture_decision",
    "task_outcome": "task_outcome",
    "module_map": "module_map",
    "risk": "risk",
    "incident": "incident",
    "memory": "memory",
}

# derivations that are durable without separate verification evidence
_DURABLE_DERIVATIONS = {"verification", "runtime_observation", "user_decision", "canonical_projection"}


def _node_type_for(ref: str) -> str:
    scheme = ref.split("://", 1)[0] if "://" in ref else "memory"
    return _MEMORY_TYPES.get(scheme, "memory")


class TwinMemoryAdapter:
    def __init__(self, twin_store, hybrid_memory=None) -> None:
        self._store = twin_store
        self._memory = hybrid_memory

    # -- recall ---------------------------------------------------------------

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        # Filter to learning memory node types so durable memory is not crowded out of the
        # candidate window by the many structural/behavioral/intent nodes.
        statuses = []
        if request.include_superseded:
            statuses = ["superseded", "invalidated", "contradicted"]
        result = self._store.query(
            TwinQuery(project_id=request.project_id, node_types=sorted(set(_MEMORY_TYPES.values())),
                      statuses=statuses, limit=max(request.limit * 4, 50),
                      min_confidence=request.min_confidence)
        )
        items: list[ContextItem] = []
        text = request.objective.lower().strip()
        for node in result.nodes:
            if node.domain != _LEARNING:
                continue
            # current facts only; superseded/invalidated stay historical unless asked
            if not request.include_superseded and node.status in {"superseded", "invalidated", "contradicted"}:
                continue
            if text and text not in f"{node.label} {node.canonical_ref}".lower():
                # cheap relevance filter; keep high-confidence facts regardless
                if node.confidence < 0.8:
                    continue
            items.append(
                ContextItem(
                    item_type=node.node_type, canonical_ref=node.canonical_ref, summary=node.label,
                    status=node.status, confidence=node.confidence, source_refs=[node.source_ref],
                    evidence_refs=node.evidence_refs, inclusion_reason="durable_memory",
                    estimated_tokens=max(1, len(node.label) // 4 + 4),
                )
            )
        items.sort(key=lambda it: it.confidence, reverse=True)
        diagnostics = []
        if self._memory is not None and text:
            # short-term recall augmentation (non-durable; advisory only)
            for hit in self._memory.retrieve_memory(query=request.objective, scope="short", limit=request.limit):
                diagnostics.append({"code": "short_term_hit", "key": hit.get("key")})
        return MemoryRecallResult(project_id=request.project_id, items=items[: request.limit], diagnostics=diagnostics)

    # -- promotion ------------------------------------------------------------

    def propose_promotion(self, request: MemoryPromotionRequest) -> MemoryPromotionDecision:
        has_evidence = bool(request.evidence_refs)
        durable = request.derivation in _DURABLE_DERIVATIONS or has_evidence

        if request.derivation in NON_VERIFIED_DERIVATIONS and not has_evidence:
            # unverified inference can never become durable memory
            return MemoryPromotionDecision(
                project_id=request.project_id, candidate_ref=request.candidate_ref, promoted=False,
                reason="unverified_inference_requires_evidence", requires_verification=True,
            )
        if not durable:
            return MemoryPromotionDecision(
                project_id=request.project_id, candidate_ref=request.candidate_ref, promoted=False,
                reason="not_durable_without_evidence", requires_verification=True,
            )

        status = "user_approved" if request.derivation == "user_decision" else "verified"
        now = datetime.now(timezone.utc)
        node = TwinNode(
            node_id=nid(request.candidate_ref), project_id=request.project_id, domain=_LEARNING,
            node_type=_node_type_for(request.candidate_ref), canonical_ref=request.candidate_ref,
            label=request.summary or request.candidate_ref, source_kind="memory",
            source_ref=request.candidate_ref, derivation=request.derivation, confidence=0.95,
            status=status, evidence_refs=request.evidence_refs, valid_from=now, created_at=now, updated_at=now,
        )
        evidence = [
            TwinEvidence(
                evidence_id=eid, project_id=request.project_id, evidence_type="memory_promotion",
                source_kind="memory", source_ref=request.candidate_ref, summary=request.summary or "",
                confidence=0.95, created_at=now,
            )
            for eid in request.evidence_refs
        ]
        self._store.apply_delta(
            TwinDelta(
                project_id=request.project_id, idempotency_key=f"promote:{request.candidate_ref}:{now.isoformat()}",
                trigger_type="memory.promoted", nodes=[node], evidence=evidence,
            )
        )
        # Mirror verified outcomes into long-term HybridMemoryStore when available.
        if self._memory is not None:
            self._memory.store_memory(key=request.candidate_ref, value={"summary": request.summary}, scope="long")
        return MemoryPromotionDecision(
            project_id=request.project_id, candidate_ref=request.candidate_ref, promoted=True,
            reason=f"promoted_as_{status}", requires_verification=False,
        )

    # -- supersede ------------------------------------------------------------

    def supersede(self, request: MemorySupersedeRequest) -> None:
        # Retire the memory from current recall while preserving audit history.
        self._store.apply_delta(
            TwinDelta(
                project_id=request.project_id,
                idempotency_key=f"supersede:{request.memory_ref}:{datetime.now(timezone.utc).isoformat()}",
                trigger_type="memory.superseded",
                invalidate_node_ids=[nid(request.memory_ref)],
                diagnostics=[{"code": "memory_superseded", "memory_ref": request.memory_ref,
                              "superseded_by": request.superseded_by_ref, "reason": request.reason}],
            )
        )
