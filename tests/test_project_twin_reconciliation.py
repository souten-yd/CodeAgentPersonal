"""PDT-10 tests for static/runtime reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.project_twin.contracts import RuntimeObservation, TwinContextRequest, TwinDelta, TwinNode, TwinQuery
from agent.project_twin.context_broker import TwinContextBroker
from agent.project_twin.reconciliation import ReconciliationService
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore

NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _inferred(ref, label="endpoint returns 200", confidence=0.6) -> TwinNode:
    return TwinNode(
        node_id=nid(ref),
        project_id="p1", domain="behavioral", node_type="behavior", canonical_ref=ref, label=label,
        source_kind="git", source_ref="api.py", derivation="heuristic_static", confidence=confidence,
        status="inferred", valid_from=NOW, created_at=NOW, updated_at=NOW,
    )


def _obs(result, oid="o1", summary="GET /x -> 200") -> RuntimeObservation:
    return RuntimeObservation(
        observation_id=oid, project_id="p1", collector="api", collector_version="1",
        observation_type="api", subject_refs=["behavior://api.py#ep"], timestamp=NOW, result=result, summary=summary,
    )


@pytest.fixture()
def store():
    s = SqliteProjectTwinStore(":memory:")
    s.apply_delta(TwinDelta(project_id="p1", idempotency_key="seed", trigger_type="seed",
                            nodes=[_inferred("behavior://api.py#ep")]))
    yield s
    s.close()


def _current(store, ref):
    res = store.query(TwinQuery(project_id="p1", canonical_refs=[ref], limit=1))
    return res.nodes[0] if res.nodes else None


def test_confirm_upgrades_inferred_to_verified_keeping_history(store):
    svc = ReconciliationService(store)
    svc.confirm("p1", "behavior://api.py#ep", _obs("passed"))
    cur = _current(store, "behavior://api.py#ep")
    assert cur.status == "verified" and cur.derivation == "runtime_observation"
    assert cur.confidence > 0.6  # verified outranks stale inference
    # the prior inferred record is kept as audit history (superseded)
    hist = store.query(TwinQuery(project_id="p1", statuses=["superseded"]))
    assert any(n.canonical_ref == "behavior://api.py#ep" and n.status == "superseded" for n in hist.nodes)


def test_contradiction_preserves_history_and_records_reality(store):
    svc = ReconciliationService(store)
    svc.contradict("p1", "behavior://api.py#ep", _obs("failed", summary="GET /x -> 500"),
                   observed_label="endpoint returns 500")
    # inferred fact is invalidated (kept historically)
    invalid = store.query(TwinQuery(project_id="p1", statuses=["invalidated"]))
    assert any(n.canonical_ref == "behavior://api.py#ep" for n in invalid.nodes)
    # observed reality is recorded
    observed = _current(store, "behavior://api.py#ep#observed")
    assert observed is not None and observed.status == "observed"
    assert observed.properties.get("contradicts") == "behavior://api.py#ep"


def test_context_identifies_contradiction(store):
    svc = ReconciliationService(store)
    svc.contradict("p1", "behavior://api.py#ep", _obs("failed"))
    broker = TwinContextBroker(store)
    sl = broker.build_slice(TwinContextRequest(project_id="p1", objective="check endpoint", phase="review", token_budget=4000))
    assert any(u.canonical_ref == "behavior://api.py#ep" for u in sl.uncertainties)


def test_repeated_observation_is_idempotent(store):
    svc = ReconciliationService(store)
    r1 = svc.confirm("p1", "behavior://api.py#ep", _obs("passed", oid="same"))
    r2 = svc.confirm("p1", "behavior://api.py#ep", _obs("passed", oid="same"))
    assert r1.revision_id == r2.revision_id  # same observation does not duplicate work


def test_new_observation_creates_new_verified_version(store):
    svc = ReconciliationService(store)
    r1 = svc.confirm("p1", "behavior://api.py#ep", _obs("passed", oid="obs1"))
    r2 = svc.confirm("p1", "behavior://api.py#ep", _obs("passed", oid="obs2"))
    assert r1.revision_id != r2.revision_id
    # only one current verified node; prior verified kept historically
    assert _current(store, "behavior://api.py#ep").status == "verified"
    hist = store.query(TwinQuery(project_id="p1", statuses=["superseded"]))
    assert sum(1 for n in hist.nodes if n.canonical_ref == "behavior://api.py#ep") >= 1
