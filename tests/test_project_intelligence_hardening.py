"""PI-24 cross-platform, scale, storage, and rollout hardening tests.

Acceptance criteria (implementation plan PI-24):
- baseline regression budget is defined and enforced;
- no project data leakage;
- no unbounded prompt growth;
- phase rollback works;
- unavailable platform evidence is explicit.
Plus: platform detection, retention/compaction, export/import + integrity, job coalescing.
"""

from __future__ import annotations

from agent.project_intelligence._persistence import ArtifactStore, apply_migrations, artifact_table_migration, connect
from agent.project_intelligence.hardening import (
    DOCKER,
    LINUX,
    ROLLOUT_STAGES,
    RUNPOD,
    WINDOWS,
    RegressionBudget,
    RolloutGate,
    assert_bounded,
    coalesce_refresh,
    compaction_plan,
    detect_platform,
    export_artifacts,
    import_artifacts,
    no_data_leakage,
    platform_evidence,
)
from agent.project_intelligence.store import ProjectIntelligenceStore


def _artifact_store():
    conn = connect(":memory:")
    apply_migrations(conn, [artifact_table_migration("t")], migration_table="t_mig")
    return ArtifactStore(conn, "t")


# --- Platform detection + explicit unavailable -------------------------------

def test_platform_detection() -> None:
    assert detect_platform({"RUNPOD_POD_ID": "x"}) == RUNPOD
    assert detect_platform({"ATLAS_IN_DOCKER": "1"}) == DOCKER
    assert detect_platform({}, platform_name="nt") == WINDOWS
    assert detect_platform({}, platform_name="posix") == LINUX


def test_unavailable_platform_evidence_is_explicit() -> None:
    ev = platform_evidence(RUNPOD, available=False)
    assert ev["result"] == "unavailable" and ev["detail"]
    ok = platform_evidence(LINUX, available=True)
    assert ok["result"] == "observed"


# --- Regression budget enforced ----------------------------------------------

def test_regression_budget_enforced() -> None:
    budget = RegressionBudget(baseline={"latency_ms": 100.0, "coverage": 0.9},
                              threshold=0.2, higher_is_better=frozenset({"coverage"}))
    # latency within +20% ok; beyond fails.
    assert budget.check("latency_ms", 110.0)[0] is True
    assert budget.check("latency_ms", 130.0)[0] is False
    # coverage must not drop more than 20%.
    assert budget.check("coverage", 0.85)[0] is True
    assert budget.check("coverage", 0.5)[0] is False
    ok, failures = budget.enforce({"latency_ms": 130.0, "coverage": 0.95})
    assert ok is False and any("latency_ms" in f for f in failures)


# --- No unbounded growth -----------------------------------------------------

def test_no_unbounded_growth() -> None:
    assert assert_bounded(800, 1000) is True
    assert assert_bounded(1200, 1000) is False


# --- Retention / compaction (non-destructive) --------------------------------

def test_compaction_plan_keeps_head_and_last_n() -> None:
    history = [{"artifact_id": f"r{i}"} for i in range(6)]
    plan = compaction_plan(history, keep_last=2, head_id="r5")
    assert "r5" in plan["retained"] and "r4" in plan["retained"]
    assert "r0" in plan["prunable"] and "r5" not in plan["prunable"]


# --- Export / import + integrity ---------------------------------------------

def test_export_import_roundtrip_and_integrity() -> None:
    store = _artifact_store()
    store.put(project_id="p1", workspace_id="w1", group_id="g", artifact_id="a1",
              artifact_type="x", payload={"v": 1})
    store.put(project_id="p1", workspace_id="w1", group_id="g", artifact_id="a2",
              artifact_type="x", payload={"v": 2})
    exported = export_artifacts(store, "p1", "g")
    assert len(exported) == 2

    target = _artifact_store()
    imported = import_artifacts(target, exported, workspace_id="w1")
    assert imported == 2
    assert target.get("p1", "a1")["payload"] == {"v": 1}
    assert target.integrity_check("p1")["status"] == "ok"


# --- Job coalescing + restart recovery ---------------------------------------

def test_job_coalescing_and_restart_recovery() -> None:
    store = ProjectIntelligenceStore()
    a = coalesce_refresh(store, project_id="p1", workspace_id="w1", job_type="twin_refresh", target_key="proj")
    b = coalesce_refresh(store, project_id="p1", workspace_id="w1", job_type="twin_refresh", target_key="proj")
    assert a == b and len(store.list_jobs("p1")) == 1  # coalesced into one job
    store.claim_job("p1", a)
    assert store.recover_running_jobs("p1") == 1  # restart recovery


# --- Phase rollback works ----------------------------------------------------

def test_rollout_gate_advances_and_rolls_back() -> None:
    gate = RolloutGate()
    assert gate.stage == "off"
    stage, advanced = gate.advance(telemetry_ok=True)
    assert advanced and stage == "shadow"
    # telemetry failure blocks advance.
    blocked_stage, advanced2 = gate.advance(telemetry_ok=False)
    assert advanced2 is False and blocked_stage == "shadow"
    # rollback returns to the prior stage.
    assert gate.rollback() == "off"


def test_rollout_stages_are_ordered() -> None:
    assert ROLLOUT_STAGES[0] == "off" and ROLLOUT_STAGES[-1] == "active"
    assert ROLLOUT_STAGES.index("shadow") < ROLLOUT_STAGES.index("active")


# --- No project data leakage -------------------------------------------------

def test_no_project_data_leakage() -> None:
    store = _artifact_store()
    store.put(project_id="p1", workspace_id="w1", group_id="g", artifact_id="a1",
              artifact_type="x", payload={"v": 1})
    # The same artifact id under a different project must not be visible.
    assert no_data_leakage(store, project_a="p1", project_b="p2", artifact_id="a1") is True
    assert store.get("p2", "a1") is None
