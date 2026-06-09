"""PDT-6 tests for twin memory integration."""

from __future__ import annotations

import pytest

from agent.project_twin.contracts import (
    MemoryPromotionRequest,
    MemoryRecallRequest,
    MemorySupersedeRequest,
    TwinQuery,
)
from agent.project_twin.memory_adapter import TwinMemoryAdapter
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore


@pytest.fixture()
def adapter():
    store = SqliteProjectTwinStore(":memory:")
    yield TwinMemoryAdapter(store), store
    store.close()


def test_unverified_inference_is_not_durable(adapter):
    mem, store = adapter
    decision = mem.propose_promotion(MemoryPromotionRequest(
        project_id="p1", candidate_ref="decision://d1", derivation="llm_inference", summary="guess"))
    assert decision.promoted is False
    assert decision.requires_verification is True
    assert decision.reason == "unverified_inference_requires_evidence"
    # nothing was written to the twin
    assert store.get_health("p1").twin_revision_id is None


def test_verified_outcome_can_be_promoted(adapter):
    mem, store = adapter
    decision = mem.propose_promotion(MemoryPromotionRequest(
        project_id="p1", candidate_ref="task_outcome://t1", derivation="verification",
        evidence_refs=["ev1"], summary="login verified by tests"))
    assert decision.promoted is True
    recalled = mem.recall(MemoryRecallRequest(project_id="p1", objective="login"))
    assert any(it.canonical_ref == "task_outcome://t1" and it.status == "verified" for it in recalled.items)


def test_inference_with_evidence_is_promotable(adapter):
    mem, store = adapter
    decision = mem.propose_promotion(MemoryPromotionRequest(
        project_id="p1", candidate_ref="decision://d2", derivation="llm_inference",
        evidence_refs=["ev2"], summary="adopt sqlite"))
    assert decision.promoted is True


def test_user_decision_is_user_approved(adapter):
    mem, store = adapter
    mem.propose_promotion(MemoryPromotionRequest(
        project_id="p1", candidate_ref="decision://d3", derivation="user_decision", summary="chosen by user"))
    recalled = mem.recall(MemoryRecallRequest(project_id="p1", objective="chosen"))
    assert any(it.canonical_ref == "decision://d3" and it.status == "user_approved" for it in recalled.items)


def test_superseded_memory_excluded_from_recall_but_historical(adapter):
    mem, store = adapter
    mem.propose_promotion(MemoryPromotionRequest(
        project_id="p1", candidate_ref="risk://r1", derivation="verification",
        evidence_refs=["ev"], summary="memory leak risk"))
    mem.supersede(MemorySupersedeRequest(project_id="p1", memory_ref="risk://r1", reason="resolved"))

    recalled = mem.recall(MemoryRecallRequest(project_id="p1", objective="memory leak"))
    assert not any(it.canonical_ref == "risk://r1" for it in recalled.items)

    historical = store.query(TwinQuery(project_id="p1", statuses=["invalidated"]))
    assert any(n.canonical_ref == "risk://r1" for n in historical.nodes)


def test_project_isolation_for_memory(adapter):
    mem, store = adapter
    mem.propose_promotion(MemoryPromotionRequest(
        project_id="p1", candidate_ref="decision://d1", derivation="verification",
        evidence_refs=["ev"], summary="p1 only"))
    other = mem.recall(MemoryRecallRequest(project_id="p2", objective="p1"))
    assert other.items == []
