"""PDT-12 tests for Nexus (external evidence) integration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.project_twin.context_broker import TwinContextBroker
from agent.project_twin.contracts import TwinContextRequest, TwinDelta, TwinNode, TwinQuery
from agent.project_twin.nexus_adapter import NexusProjector
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore

NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)
RETRIEVED = "2026-06-01T00:00:00+00:00"


def _seed_requirement(store, ref="requirement://r1"):
    store.apply_delta(TwinDelta(project_id="p1", idempotency_key=f"seed:{ref}", trigger_type="seed", nodes=[
        TwinNode(node_id=nid(ref), project_id="p1", domain="intent_delivery", node_type="requirement",
                 canonical_ref=ref, label="must support login", source_kind="atlas", source_ref="r1",
                 derivation="canonical_projection", confidence=1.0, status="declared",
                 valid_from=NOW, created_at=NOW, updated_at=NOW)]))


@pytest.fixture()
def store():
    s = SqliteProjectTwinStore(":memory:")
    yield s
    s.close()


def test_evidence_retains_source_and_links_support(store):
    _seed_requirement(store)
    NexusProjector(store).add_evidence(
        "p1", evidence_id="e1", summary="OAuth best practice", content_hash="abc123",
        retrieved_at=RETRIEVED, supports=["requirement://r1"], document_id="d1")
    ev = store.query(TwinQuery(project_id="p1", node_types=["nexus_evidence"])).nodes[0]
    assert ev.properties["content_hash"] == "abc123"
    assert ev.properties["retrieved_at"] == RETRIEVED
    assert ev.properties["external"] is True
    et = {(e.edge_type, e.source_node_id, e.target_node_id) for e in store.get_snapshot("p1").edges}
    assert ("supports", nid("nexus_evidence://e1"), nid("requirement://r1")) in et


def test_nexus_claims_do_not_become_verified_code_truth(store):
    _seed_requirement(store)
    NexusProjector(store).add_evidence(
        "p1", evidence_id="e1", summary="claim", content_hash="h", retrieved_at=RETRIEVED,
        supports=["requirement://r1"])
    # the requirement is unchanged: still declared, not verified
    req = store.query(TwinQuery(project_id="p1", canonical_refs=["requirement://r1"], limit=1)).nodes[0]
    assert req.status == "declared"
    # the support edge itself is inferred (llm_inference), never verified
    edge = next(e for e in store.get_snapshot("p1").edges if e.edge_type == "supports")
    assert edge.derivation == "llm_inference" and edge.status == "inferred"


def test_contradiction_is_explicit(store):
    _seed_requirement(store, "decision://d1")
    NexusProjector(store).add_evidence(
        "p1", evidence_id="e2", summary="counter-evidence", content_hash="h2", retrieved_at=RETRIEVED,
        contradicts=["decision://d1"])
    et = {e.edge_type for e in store.get_snapshot("p1").edges}
    assert "contradicts" in et


def test_architecture_decision_evidence(store):
    store.apply_delta(TwinDelta(project_id="p1", idempotency_key="seed-d", trigger_type="seed", nodes=[
        TwinNode(node_id=nid("decision://d1"), project_id="p1", domain="learning", node_type="architecture_decision",
                 canonical_ref="decision://d1", label="use sqlite", source_kind="memory", source_ref="d1",
                 derivation="user_decision", confidence=0.95, status="user_approved",
                 valid_from=NOW, created_at=NOW, updated_at=NOW)]))
    NexusProjector(store).add_evidence(
        "p1", evidence_id="e3", summary="sqlite scaling note", content_hash="h3", retrieved_at=RETRIEVED,
        supports=["decision://d1"])
    et = {(e.edge_type, e.target_node_id) for e in store.get_snapshot("p1").edges}
    assert ("supports", nid("decision://d1")) in et


def test_context_broker_nexus_section(store):
    _seed_requirement(store)
    NexusProjector(store).add_evidence(
        "p1", evidence_id="e1", summary="external note", content_hash="h", retrieved_at=RETRIEVED,
        supports=["requirement://r1"])
    sl = TwinContextBroker(store).build_slice(
        TwinContextRequest(project_id="p1", objective="login", phase="project_investigation", token_budget=4000))
    assert any(it.canonical_ref == "nexus_evidence://e1" for it in sl.nexus_evidence)
