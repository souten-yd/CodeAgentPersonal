"""Nexus (external evidence) integration (PDT-12).

Projects Nexus documents, evidence and reports into the twin `learning` domain as
references that retain their external source, retrieval date and content hash, and links
them to requirements/decisions with explicit `supports`/`contradicts` edges.

Safety: external claims never become verified code truth automatically. Nexus nodes are
external observations of documents (not of the running code); the support/contradict edges
are `llm_inference` with confidence < 1.0 and they never change the status of the target
code/requirement fact. Contradictions remain explicit.

The store delegates nothing here; this is a projector that the caller drives with Nexus
records. Implements a thin surface usable behind a research-agent integration.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.project_twin.contracts import TwinDelta, TwinEdge, TwinEvidence, TwinNode, TwinRevision
from agent.project_twin.static_graph import nid

_DOMAIN = "learning"


def _doc_ref(did: str) -> str:
    return f"nexus_document://{did}"


def _ev_ref(eid: str) -> str:
    return f"nexus_evidence://{eid}"


def _report_ref(rid: str) -> str:
    return f"nexus_report://{rid}"


class NexusProjector:
    def __init__(self, store) -> None:
        self._store = store

    def _node(self, project_id, *, node_type, ref, label, props, status="declared", confidence=0.7, now=None) -> TwinNode:
        now = now or datetime.now(timezone.utc)
        return TwinNode(
            node_id=nid(ref), project_id=project_id, domain=_DOMAIN, node_type=node_type,
            canonical_ref=ref, label=label, properties=props, source_kind="nexus", source_ref=ref,
            derivation="canonical_projection", confidence=confidence, status=status,
            valid_from=now, created_at=now, updated_at=now,
        )

    def _edge(self, project_id, *, edge_type, source_ref, target_ref, confidence, now) -> TwinEdge:
        # The support/contradict relationship to a code/requirement fact is inferred and
        # never upgrades the target to verified.
        return TwinEdge(
            edge_id=nid(f"{edge_type}|{source_ref}|{target_ref}"), project_id=project_id, domain=_DOMAIN,
            source_node_id=nid(source_ref), target_node_id=nid(target_ref), edge_type=edge_type,
            source_kind="nexus", source_ref=source_ref, derivation="llm_inference",
            confidence=confidence, status="inferred", valid_from=now, created_at=now, updated_at=now,
        )

    def add_document(self, project_id, *, document_id, title, url, content_hash, retrieved_at) -> TwinRevision:
        now = datetime.now(timezone.utc)
        node = self._node(project_id, node_type="nexus_document", ref=_doc_ref(document_id), label=title,
                          props={"url": url, "content_hash": content_hash, "retrieved_at": retrieved_at, "external": True}, now=now)
        return self._store.apply_delta(TwinDelta(
            project_id=project_id, idempotency_key=f"nexus_doc:{document_id}:{content_hash}",
            trigger_type="nexus.evidence.added", nodes=[node]))

    def add_evidence(self, project_id, *, evidence_id, summary, content_hash, retrieved_at,
                     supports=None, contradicts=None, document_id=None, confidence=0.7) -> TwinRevision:
        now = datetime.now(timezone.utc)
        ev_ref = _ev_ref(evidence_id)
        node = self._node(project_id, node_type="nexus_evidence", ref=ev_ref, label=summary,
                          props={"content_hash": content_hash, "retrieved_at": retrieved_at, "external": True},
                          status="observed", confidence=confidence, now=now)
        edges: list[TwinEdge] = []
        if document_id:
            edges.append(self._edge(project_id, edge_type="cited_from", source_ref=ev_ref,
                                    target_ref=_doc_ref(document_id), confidence=confidence, now=now))
        for target in supports or []:
            edges.append(self._edge(project_id, edge_type="supports", source_ref=ev_ref, target_ref=target, confidence=confidence, now=now))
        for target in contradicts or []:
            edges.append(self._edge(project_id, edge_type="contradicts", source_ref=ev_ref, target_ref=target, confidence=confidence, now=now))
        evidence = [TwinEvidence(
            evidence_id=evidence_id, project_id=project_id, evidence_type="nexus", source_kind="nexus",
            source_ref=ev_ref, summary=summary, content_hash=content_hash, confidence=confidence,
            observed_at=None, created_at=now,
        )]
        return self._store.apply_delta(TwinDelta(
            project_id=project_id, idempotency_key=f"nexus_ev:{evidence_id}:{content_hash}",
            trigger_type="nexus.evidence.added", nodes=[node], edges=edges, evidence=evidence))

    def add_report(self, project_id, *, report_id, title, content_hash, retrieved_at, evidence_ids=None) -> TwinRevision:
        now = datetime.now(timezone.utc)
        rep_ref = _report_ref(report_id)
        node = self._node(project_id, node_type="nexus_report", ref=rep_ref, label=title,
                          props={"content_hash": content_hash, "retrieved_at": retrieved_at, "external": True}, now=now)
        edges = [self._edge(project_id, edge_type="includes_evidence", source_ref=rep_ref,
                           target_ref=_ev_ref(eid), confidence=0.7, now=now) for eid in (evidence_ids or [])]
        return self._store.apply_delta(TwinDelta(
            project_id=project_id, idempotency_key=f"nexus_report:{report_id}:{content_hash}",
            trigger_type="nexus.evidence.added", nodes=[node], edges=edges))
