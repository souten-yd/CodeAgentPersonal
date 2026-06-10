"""PI-8 runtime intelligence and reconciliation v2 tests.

Acceptance criteria (implementation plan PI-8):
- real verification result is ingested automatically;
- unavailable remains unavailable throughout UI and rollup;
- contradicted static fact is retained historically;
- verified path requires matching revision evidence;
- collector failure cannot mark task success.
"""

from __future__ import annotations

from agent.project_twin.runtime.collectors import (
    map_stack_frames,
    map_symbol_ref,
    normalize_api,
    normalize_pytest,
    safe_collect,
    unavailable_observation,
)
from agent.project_twin.runtime.reconciliation import (
    CONFIRM,
    CONTRADICT,
    CONTRADICTED,
    STALE,
    UNAVAILABLE,
    VERIFIED,
    reconcile,
    summarize_rollup,
)


# --- Ingest real verification results ----------------------------------------

def test_pytest_results_ingested_and_mapped() -> None:
    report = {"tests": [
        {"nodeid": "tests/test_a.py::test_x", "outcome": "passed"},
        {"nodeid": "tests/test_a.py::test_y", "outcome": "failed", "longrepr": "AssertionError"},
    ]}
    obs = normalize_pytest(report, project_id="p1", workspace_id="w1", source_revision="rev1",
                           coverage={"app.py": ["handler"]})
    results = {o.summary: o.result for o in obs}
    assert results["tests/test_a.py::test_x"] == "passed"
    assert results["tests/test_a.py::test_y"] == "failed"
    # coverage maps to the static symbol ref.
    assert any(map_symbol_ref("app.py", "handler") in o.subject_refs for o in obs)
    assert all(o.source_revision == "rev1" for o in obs)  # revision preserved


def test_api_observation_normalized() -> None:
    o = normalize_api({"method": "GET", "path": "/users", "status_code": 200},
                      project_id="p1", workspace_id="w1", source_revision="rev1")
    assert o.result == "passed"
    bad = normalize_api({"method": "GET", "path": "/x", "status_code": 500},
                        project_id="p1", workspace_id="w1", source_revision="rev1")
    assert bad.result == "failed"


def test_stack_frames_mapped_to_symbols() -> None:
    refs = map_stack_frames([{"file": "svc.py", "function": "run"}, {"file": "x.txt", "function": "n"}])
    assert "py://svc.py#run" in refs and len(refs) == 1


# --- Confirm requires matching revision --------------------------------------

def test_confirm_requires_matching_revision() -> None:
    obs = normalize_pytest({"tests": [{"nodeid": "t::a", "outcome": "passed"}]},
                           project_id="p1", workspace_id="w1", source_revision="rev2",
                           coverage={"app.py": ["handler"]})
    fact = map_symbol_ref("app.py", "handler")
    # Matching revision -> verified.
    ok = reconcile(fact, obs, current_source_revision="rev2")
    assert ok.decision in (CONFIRM, "partially_confirm") and ok.status == VERIFIED
    # Stale revision -> not verified.
    stale = reconcile(fact, obs, current_source_revision="rev3")
    assert stale.decision == STALE and stale.status != VERIFIED


# --- Contradiction retained historically -------------------------------------

def test_contradiction_retains_history() -> None:
    obs = normalize_pytest({"tests": [{"nodeid": "t::a", "outcome": "failed"}]},
                           project_id="p1", workspace_id="w1", source_revision="rev1",
                           coverage={"app.py": ["handler"]})
    fact = map_symbol_ref("app.py", "handler")
    out = reconcile(fact, obs, current_source_revision="rev1", prior_status="inferred")
    assert out.decision == CONTRADICT and out.status == CONTRADICTED
    assert "inferred" in out.history and CONTRADICTED in out.history


# --- Unavailable stays unavailable -------------------------------------------

def test_unavailable_never_becomes_passed() -> None:
    unav = unavailable_observation("playwright", "browser missing", project_id="p1", workspace_id="w1",
                                   source_revision="rev1", subject_refs=["py://app#handler"])
    assert unav.result == "unavailable"
    out = reconcile("py://app#handler", [unav], current_source_revision="rev1")
    assert out.decision == UNAVAILABLE and out.status != VERIFIED


def test_rollup_unavailable_blocks_success() -> None:
    passed = normalize_pytest({"tests": [{"nodeid": "t::a", "outcome": "passed"}]},
                              project_id="p1", workspace_id="w1", source_revision="rev1")
    unav = [unavailable_observation("api", "endpoint down", project_id="p1", workspace_id="w1")]
    roll = summarize_rollup(passed + unav)
    assert roll.unavailable == 1
    assert roll.success is False  # unavailable forces non-success everywhere
    # An all-passed rollup is success.
    assert summarize_rollup(passed).success is True


# --- Collector failure cannot mark success -----------------------------------

def test_collector_failure_yields_unavailable_not_success() -> None:
    def boom():
        raise RuntimeError("collector crashed")

    obs = safe_collect("playwright", boom, project_id="p1", workspace_id="w1", source_revision="rev1")
    assert len(obs) == 1 and obs[0].result == "unavailable"
    assert summarize_rollup(obs).success is False


def test_partial_confirm_when_multiple_subjects() -> None:
    obs = normalize_pytest({"tests": [{"nodeid": "t::a", "outcome": "passed"}]},
                           project_id="p1", workspace_id="w1", source_revision="rev1",
                           coverage={"app.py": ["handler", "other"]})
    fact = map_symbol_ref("app.py", "handler")
    out = reconcile(fact, obs, current_source_revision="rev1")
    assert out.status == VERIFIED
    assert out.decision in (CONFIRM, "partially_confirm")
