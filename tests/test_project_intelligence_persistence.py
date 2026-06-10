"""PI-2 persistence and migration foundation tests.

Acceptance criteria (implementation plan PI-2):
- transaction failure leaves no partial revision;
- duplicate idempotency key is harmless;
- stale parent revision is rejected;
- project isolation holds;
- migrations are repeatable and rollback-safe;
plus: immutable revision rows, point-in-time reads, integrity/corruption signal, and a
restart-safe job journal (ADR-PI-011). SQLite stays an internal adapter (ADR-PI-015).
"""

from __future__ import annotations

import pytest

from agent.architecture_blueprint.store import BlueprintStore
from agent.project_convergence.store import ConvergenceStore
from agent.project_intelligence._persistence import (
    StoreError,
    apply_migrations,
    connect,
    current_schema_version,
)
from agent.project_intelligence.store import ProjectIntelligenceStore
from agent.architecture_blueprint.migrations import (
    MIGRATION_TABLE as BP_MIGRATION_TABLE,
    SCHEMA_MIGRATIONS as BP_MIGRATIONS,
)


# --- Blueprint immutable revisions + stale parent + idempotency --------------

def test_blueprint_revisions_are_immutable_and_headed() -> None:
    s = BlueprintStore()
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1",
                    revision_id="r1", payload={"v": 1})
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1",
                    revision_id="r2", payload={"v": 2}, parent_revision_id="r1",
                    expected_parent_id="r1")
    active = s.get_active("p1", "w1", "b1")
    assert active is not None and active["artifact_id"] == "r2"
    assert s.get_revision("p1", "r1")["payload"] == {"v": 1}  # parent unchanged
    assert [r["artifact_id"] for r in s.list_revisions("p1", "b1")] == ["r1", "r2"]


def test_blueprint_stale_parent_is_rejected() -> None:
    s = BlueprintStore()
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1", revision_id="r1", payload={})
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1", revision_id="r2",
                    parent_revision_id="r1", expected_parent_id="r1", payload={})
    # head is now r2; basing a new revision on r1 is stale.
    with pytest.raises(StoreError) as exc:
        s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1", revision_id="r3",
                        parent_revision_id="r1", expected_parent_id="r1", payload={})
    assert exc.value.code == "stale_revision"
    assert s.get_active("p1", "w1", "b1")["artifact_id"] == "r2"  # head unmoved
    assert s.get_revision("p1", "r3") is None


def test_duplicate_idempotency_key_is_harmless() -> None:
    s = BlueprintStore()
    a = s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1",
                        revision_id="r1", payload={"v": 1}, idempotency_key="k1")
    b = s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1",
                        revision_id="r1-dup", payload={"v": 999}, idempotency_key="k1")
    assert a == b == "r1"
    # The duplicate did not create a second row nor mutate the original.
    assert len(s.list_revisions("p1", "b1")) == 1
    assert s.get_revision("p1", "r1")["payload"] == {"v": 1}


def test_transaction_failure_leaves_no_partial_revision() -> None:
    s = BlueprintStore()
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1",
                    revision_id="r1", payload={"v": 1})
    # Reusing an artifact_id violates immutability (UNIQUE) -> whole tx rolls back.
    with pytest.raises(StoreError) as exc:
        s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1",
                        revision_id="r1", payload={"v": 2})
    assert exc.value.code == "immutability_violation"
    # No partial write: still exactly one row, original payload, head still r1.
    assert len(s.list_revisions("p1", "b1")) == 1
    assert s.get_revision("p1", "r1")["payload"] == {"v": 1}
    assert s.get_active("p1", "w1", "b1")["artifact_id"] == "r1"


# --- Project isolation -------------------------------------------------------

def test_project_isolation_blueprint() -> None:
    s = BlueprintStore()
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1", revision_id="r1", payload={"x": 1})
    s.save_revision(project_id="p2", workspace_id="w1", blueprint_id="b1", revision_id="r1", payload={"x": 2})
    # Same artifact_id in two projects must not collide or leak.
    assert s.get_revision("p1", "r1")["payload"] == {"x": 1}
    assert s.get_revision("p2", "r1")["payload"] == {"x": 2}
    assert s.get_revision("p1", "r1") != s.get_revision("p2", "r1")
    assert s.get_active("p2", "w1", "b1")["project_id"] == "p2"


# --- Point-in-time + integrity -----------------------------------------------

def test_point_in_time_and_integrity_ok() -> None:
    times = iter(["2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00"])
    s = BlueprintStore(now_fn=lambda: next(times))
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1", revision_id="r1", payload={"v": 1})
    s.save_revision(project_id="p1", workspace_id="w1", blueprint_id="b1", revision_id="r2",
                    parent_revision_id="r1", expected_parent_id="r1", payload={"v": 2})
    as_of = s.revision_as_of("p1", "b1", "2026-01-15T00:00:00+00:00")
    assert as_of is not None and as_of["artifact_id"] == "r1"
    assert s.integrity_check("p1")["status"] == "ok"


# --- Convergence report history ----------------------------------------------

def test_convergence_reports_history_and_latest() -> None:
    s = ConvergenceStore()
    s.save_report(project_id="p1", workspace_id="w1", blueprint_revision_id="br1",
                  report_id="rep1", payload={"score": 0.1})
    s.save_report(project_id="p1", workspace_id="w1", blueprint_revision_id="br1",
                  report_id="rep2", payload={"score": 0.9})
    latest = s.get_latest("p1", "w1", "br1")
    assert latest["artifact_id"] == "rep2"
    assert len(s.list_reports("p1", "br1")) == 2
    assert s.integrity_check("p1")["status"] == "ok"


# --- Project Intelligence job journal (restart-safe) -------------------------

def test_pi_job_journal_enqueue_claim_complete_idempotent() -> None:
    s = ProjectIntelligenceStore()
    s.enqueue_job(project_id="p1", workspace_id="w1", job_id="j1", job_type="refresh", idempotency_key="k1")
    dup = s.enqueue_job(project_id="p1", workspace_id="w1", job_id="j1-dup", job_type="refresh", idempotency_key="k1")
    assert dup == "j1"  # duplicate idempotency key returns the prior job
    assert len(s.list_jobs("p1")) == 1

    claimed = s.claim_job("p1", "j1")
    assert claimed["status"] == "running" and claimed["attempts"] == 1
    # A running job cannot be claimed again.
    assert s.claim_job("p1", "j1") is None
    s.complete_job("p1", "j1", status="done")
    assert s.get_job("p1", "j1")["status"] == "done"


def test_pi_jobs_recover_after_restart() -> None:
    s = ProjectIntelligenceStore()
    s.enqueue_job(project_id="p1", workspace_id="w1", job_id="j1", job_type="refresh")
    s.claim_job("p1", "j1")  # now running; simulate crash before completion
    recovered = s.recover_running_jobs("p1")
    assert recovered == 1
    assert s.get_job("p1", "j1")["status"] == "queued"
    # Recovery is idempotent: a second call requeues nothing.
    assert s.recover_running_jobs("p1") == 0


def test_pi_manifest_is_immutable_artifact() -> None:
    s = ProjectIntelligenceStore()
    s.save_manifest(project_id="p1", workspace_id="w1", phase="planning",
                    manifest_id="m1", payload={"budget": 8000})
    with pytest.raises(StoreError):
        s.save_manifest(project_id="p1", workspace_id="w1", phase="planning",
                        manifest_id="m1", payload={"budget": 9999})
    assert s.get_manifest("p1", "m1")["payload"] == {"budget": 8000}


# --- Migrations are repeatable and rollback-safe -----------------------------

def test_migrations_are_repeatable() -> None:
    conn = connect(":memory:")
    v1 = apply_migrations(conn, BP_MIGRATIONS, migration_table=BP_MIGRATION_TABLE)
    v2 = apply_migrations(conn, BP_MIGRATIONS, migration_table=BP_MIGRATION_TABLE)  # no-op
    assert v1 == v2 == current_schema_version(conn, BP_MIGRATION_TABLE)
    assert v1 >= 1


def test_failed_migration_rolls_back_and_is_not_recorded() -> None:
    conn = connect(":memory:")
    good_then_bad = [
        (1, ["CREATE TABLE IF NOT EXISTS ok_tbl (id INTEGER PRIMARY KEY)"]),
        (2, ["CREATE TABLE bad_tbl (id INTEGER PRIMARY KEY)", "THIS IS NOT VALID SQL"]),
    ]
    with pytest.raises(Exception):
        apply_migrations(conn, good_then_bad, migration_table="t_mig")
    # version 1 applied; version 2 rolled back and not recorded; bad_tbl absent.
    assert current_schema_version(conn, "t_mig") == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "ok_tbl" in tables
    assert "bad_tbl" not in tables
