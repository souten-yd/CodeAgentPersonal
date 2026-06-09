"""Static/runtime reconciliation (PDT-10).

Combines inferred static/behavioral facts with runtime observations truthfully:
- confirm: a runtime observation that agrees with an inferred fact upgrades it to a
  verified fact (the prior inferred record is superseded, kept as audit history);
- contradict: an observation that disagrees invalidates the inferred fact (kept as
  history) and records the observed reality with evidence;
- confidence is recalculated; verified observation outranks stale inference but never
  deletes audit history;
- re-ingesting the same observation is idempotent (keyed by observation id).

Reconciliation diagnostics record every decision.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.project_twin.contracts import (
    RuntimeObservation,
    TwinDelta,
    TwinEvidence,
    TwinNode,
    TwinQuery,
    TwinRevision,
)
from agent.project_twin.static_graph import nid

_VERIFIED_CONFIDENCE = 0.95
_OBSERVED_CONFIDENCE = 0.9


class ReconciliationService:
    def __init__(self, store) -> None:
        self._store = store

    def _current_node(self, project_id: str, canonical_ref: str) -> TwinNode | None:
        res = self._store.query(TwinQuery(project_id=project_id, canonical_refs=[canonical_ref], limit=1))
        return res.nodes[0] if res.nodes else None

    @staticmethod
    def _evidence(project_id: str, obs: RuntimeObservation, now: datetime) -> TwinEvidence:
        return TwinEvidence(
            evidence_id=obs.observation_id, project_id=project_id, evidence_type="runtime_observation",
            source_kind=obs.collector, source_ref=obs.observation_type, summary=obs.summary,
            content_hash=None, confidence=_VERIFIED_CONFIDENCE, observed_at=obs.timestamp, created_at=now,
        )

    def confirm(self, project_id: str, canonical_ref: str, observation: RuntimeObservation) -> TwinRevision:
        """Upgrade an inferred fact to verified using a confirming observation."""

        now = datetime.now(timezone.utc)
        existing = self._current_node(project_id, canonical_ref)
        domain = existing.domain if existing else "runtime"
        node_type = existing.node_type if existing else "observed_fact"
        label = existing.label if existing else canonical_ref
        properties = dict(existing.properties) if existing else {}
        properties["reconciled_from"] = existing.status if existing else "new"

        verified = TwinNode(
            node_id=nid(canonical_ref), project_id=project_id, domain=domain, node_type=node_type,
            canonical_ref=canonical_ref, label=label, properties=properties, source_kind=observation.collector,
            source_ref=observation.observation_id, derivation="runtime_observation",
            confidence=_VERIFIED_CONFIDENCE, status="verified", evidence_refs=[observation.observation_id],
            observed_at=observation.timestamp, valid_from=now, created_at=now, updated_at=now,
        )
        return self._store.apply_delta(TwinDelta(
            project_id=project_id, idempotency_key=f"reconcile_confirm:{canonical_ref}:{observation.observation_id}",
            trigger_type="reconciliation.confirm", nodes=[verified],
            evidence=[self._evidence(project_id, observation, now)],
            observations=[observation],
            diagnostics=[{"code": "fact_verified", "canonical_ref": canonical_ref, "observation": observation.observation_id}],
        ))

    def contradict(
        self,
        project_id: str,
        inferred_ref: str,
        observation: RuntimeObservation,
        *,
        observed_ref: str | None = None,
        observed_label: str = "",
    ) -> TwinRevision:
        """Invalidate an inferred fact contradicted by an observation and record reality."""

        now = datetime.now(timezone.utc)
        existing = self._current_node(project_id, inferred_ref)
        observed_ref = observed_ref or f"{inferred_ref}#observed"
        domain = existing.domain if existing else "runtime"
        node_type = existing.node_type if existing else "observed_fact"

        observed = TwinNode(
            node_id=nid(observed_ref), project_id=project_id, domain=domain, node_type=node_type,
            canonical_ref=observed_ref, label=observed_label or f"observed: {observation.summary}",
            properties={"contradicts": inferred_ref}, source_kind=observation.collector,
            source_ref=observation.observation_id, derivation="runtime_observation",
            confidence=_OBSERVED_CONFIDENCE, status="observed", evidence_refs=[observation.observation_id],
            observed_at=observation.timestamp, valid_from=now, created_at=now, updated_at=now,
        )
        invalidate = [existing.node_id] if existing else []
        return self._store.apply_delta(TwinDelta(
            project_id=project_id,
            idempotency_key=f"reconcile_contradict:{inferred_ref}:{observation.observation_id}",
            trigger_type="reconciliation.contradict", nodes=[observed],
            invalidate_node_ids=invalidate,
            evidence=[self._evidence(project_id, observation, now)],
            observations=[observation],
            diagnostics=[{
                "code": "fact_contradicted", "inferred_ref": inferred_ref, "observed_ref": observed_ref,
                "observation": observation.observation_id,
            }],
        ))
