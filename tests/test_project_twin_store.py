"""PDT-2 tests for the local transactional Twin Store (SQLite).

Covers: atomic delta, no partial revision on failure, stable idempotency, project
isolation/scope, stale-base rejection, supersede history, invalidation, point-in-time
snapshot, query filtering/pagination, health, and migration rollback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlite3

import pytest

from agent.project_twin.contracts import (
    RuntimeObservation,
    TwinDelta,
    TwinEdge,
    TwinEvidence,
    TwinNode,
    TwinQuery,
)
from agent.project_twin.migrations import apply_migrations, current_schema_version
from agent.project_twin.store import SqliteProjectTwinStore, TwinStoreError

NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


def _node(project_id="p1", node_id="n1", canonical_ref="py://mod.f", **over) -> TwinNode:
    base = dict(
        node_id=node_id,
        project_id=project_id,
        domain="structural",
        node_type="function",
        canonical_ref=canonical_ref,
        label="f",
        source_kind="git",
        source_ref="mod.py",
        derivation="deterministic_static",
        confidence=0.9,
        status="declared",
        valid_from=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(over)
    return TwinNode(**base)


def _edge(project_id="p1", **over) -> TwinEdge:
    base = dict(
        edge_id="e1",
        project_id=project_id,
        domain="structural",
        source_node_id="n1",
        target_node_id="n2",
        edge_type="calls",
        source_kind="git",
        source_ref="mod.py",
        derivation="deterministic_static",
        confidence=0.8,
        status="declared",
        valid_from=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(over)
    return TwinEdge(**base)


def _delta(project_id="p1", idem="k1", **over) -> TwinDelta:
    base = dict(project_id=project_id, idempotency_key=idem, trigger_type="workspace.changed")
    base.update(over)
    return TwinDelta(**base)


@pytest.fixture()
def store() -> SqliteProjectTwinStore:
    s = SqliteProjectTwinStore(":memory:")
    yield s
    s.close()


# --- basic apply + health + snapshot -----------------------------------------

def test_apply_delta_creates_revision_and_updates_head(store):
    rev = store.apply_delta(_delta(nodes=[_node()], edges=[_edge()]))
    assert rev.node_upserts == 1 and rev.edge_upserts == 1
    health = store.get_health("p1")
    assert health.status == "ok"
    assert health.twin_revision_id == rev.revision_id
    assert health.node_count == 1 and health.edge_count == 1


def test_snapshot_returns_current_facts(store):
    store.apply_delta(_delta(nodes=[_node()], edges=[_edge()]))
    snap = store.get_snapshot("p1")
    assert [n.canonical_ref for n in snap.nodes] == ["py://mod.f"]
    assert [e.edge_type for e in snap.edges] == ["calls"]


def test_health_for_unknown_project_is_not_found(store):
    health = store.get_health("missing")
    assert health.status == "not_found"
    assert any(d["code"] == "project_not_found" for d in health.diagnostics)


# --- idempotency -------------------------------------------------------------

def test_idempotent_delta_is_stable(store):
    d = _delta(nodes=[_node()])
    rev1 = store.apply_delta(d)
    rev2 = store.apply_delta(_delta(nodes=[_node()], idem="k1"))
    assert rev1.revision_id == rev2.revision_id
    # No duplicate node was inserted.
    assert store.get_health("p1").node_count == 1


# --- stale base revision -----------------------------------------------------

def test_stale_base_revision_rejected(store):
    rev1 = store.apply_delta(_delta(nodes=[_node()]))
    with pytest.raises(TwinStoreError) as exc:
        store.apply_delta(_delta(idem="k2", base_revision_id="does-not-match", nodes=[_node(canonical_ref="py://mod.g")]))
    assert exc.value.code == "stale_base_revision"
    # Correct base is accepted.
    rev2 = store.apply_delta(_delta(idem="k3", base_revision_id=rev1.revision_id, nodes=[_node(canonical_ref="py://mod.g")]))
    assert rev2.parent_revision_id == rev1.revision_id


# --- project isolation / scope ----------------------------------------------

def test_payload_scope_violation_rejected(store):
    with pytest.raises(TwinStoreError) as exc:
        store.apply_delta(_delta(project_id="p1", nodes=[_node(project_id="p2")]))
    assert exc.value.code == "project_scope_violation"


def test_projects_are_isolated(store):
    store.apply_delta(_delta(project_id="p1", idem="a", nodes=[_node(project_id="p1", canonical_ref="py://p1.f")]))
    store.apply_delta(_delta(project_id="p2", idem="b", nodes=[_node(project_id="p2", canonical_ref="py://p2.g")]))
    snap1 = store.get_snapshot("p1")
    snap2 = store.get_snapshot("p2")
    assert [n.canonical_ref for n in snap1.nodes] == ["py://p1.f"]
    assert [n.canonical_ref for n in snap2.nodes] == ["py://p2.g"]


# --- supersede history + invalidation ----------------------------------------

def test_supersede_preserves_history(store):
    store.apply_delta(_delta(idem="a", nodes=[_node(label="old", confidence=0.5)]))
    store.apply_delta(_delta(idem="b", nodes=[_node(label="new", confidence=0.95)]))
    snap = store.get_snapshot("p1")
    assert len(snap.nodes) == 1 and snap.nodes[0].label == "new"
    # Historical view still includes the superseded record.
    historical = store.query(TwinQuery(project_id="p1", statuses=["superseded"]))
    assert any(n.label == "old" and n.status == "superseded" for n in historical.nodes)


def test_invalidation_marks_and_counts(store):
    store.apply_delta(_delta(idem="a", nodes=[_node(node_id="n1")]))
    rev = store.apply_delta(_delta(idem="b", invalidate_node_ids=["n1"]))
    assert rev.invalidations == 1
    assert store.get_health("p1").node_count == 0
    invalidated = store.query(TwinQuery(project_id="p1", statuses=["invalidated"]))
    assert any(n.node_id == "n1" and n.status == "invalidated" for n in invalidated.nodes)


# --- atomicity: failure leaves no partial revision ---------------------------

def test_failure_rolls_back_with_no_partial_revision(store, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(store, "_apply_observations", boom)
    with pytest.raises(RuntimeError):
        store.apply_delta(_delta(nodes=[_node()]))
    # Nothing was committed: no project head, no nodes, no revisions.
    assert store.get_health("p1").twin_revision_id is None
    assert store.get_health("p1").node_count == 0
    rev_count = store._conn.execute("SELECT COUNT(*) AS c FROM twin_revisions").fetchone()["c"]
    assert rev_count == 0


# --- point-in-time snapshot --------------------------------------------------

def test_point_in_time_snapshot(store):
    counter = {"n": 0}

    def clock() -> str:
        counter["n"] += 1
        return (NOW + timedelta(seconds=counter["n"])).isoformat()

    s = SqliteProjectTwinStore(":memory:", now_fn=clock)
    rev1 = s.apply_delta(_delta(idem="a", nodes=[_node(label="v1")]))
    s.apply_delta(_delta(idem="b", nodes=[_node(label="v2")]))
    # At rev1 the node was still "v1".
    snap = s.get_snapshot("p1", revision_id=rev1.revision_id)
    assert len(snap.nodes) == 1 and snap.nodes[0].label == "v1"
    s.close()


# --- query pagination --------------------------------------------------------

def test_query_pagination(store):
    nodes = [_node(node_id=f"n{i}", canonical_ref=f"py://mod.f{i}") for i in range(5)]
    store.apply_delta(_delta(nodes=nodes))
    page1 = store.query(TwinQuery(project_id="p1", limit=2))
    assert len(page1.nodes) == 2 and page1.truncated and page1.cursor == "2"
    page2 = store.query(TwinQuery(project_id="p1", limit=2, cursor=page1.cursor))
    assert len(page2.nodes) == 2 and page2.cursor == "4"
    page3 = store.query(TwinQuery(project_id="p1", limit=2, cursor=page2.cursor))
    assert len(page3.nodes) == 1 and not page3.truncated and page3.cursor is None


# --- migration rollback ------------------------------------------------------

def test_migration_rollback_on_failure():
    conn = sqlite3.connect(":memory:")
    good_then_bad = [
        (1, ["CREATE TABLE ok1 (a TEXT)"]),
        (2, ["CREATE TABLE ok2 (b TEXT)", "THIS IS NOT VALID SQL"]),
    ]
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(conn, good_then_bad, now_iso=NOW.isoformat())
    # Version 1 committed; version 2 rolled back (table absent, version unrecorded).
    assert current_schema_version(conn) == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "ok1" in tables and "ok2" not in tables
    conn.close()
