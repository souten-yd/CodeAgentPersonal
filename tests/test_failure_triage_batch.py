"""Deterministic tests for batch failure triage routing (stubbed judge, no real model)."""
from __future__ import annotations

from agent.twin_control_plane.failure_classifier import ENVIRONMENT, GENUINELY_BROKEN, SNAPSHOT_DRIFT
from agent.twin_control_plane.failure_triage_batch import (
    classification_confidence, estimate_cost, triage_failures,
)


def test_confidence_high_when_marker_matches():
    assert classification_confidence("ConnectionRefusedError: max retries") == "high"
    assert classification_confidence("<!doctype html> ...") == "high"


def test_confidence_low_when_no_marker():
    assert classification_confidence("AssertionError: assert 1 == 2") == "low"
    assert classification_confidence("") == "low"


def test_high_confidence_failures_are_not_escalated():
    failures = [("t1", "ConnectionRefusedError: max retries exceeded"),
                ("t2", "<!doctype html> drift")]

    def judge(reason, test_id):  # pragma: no cover - must not be called
        raise AssertionError("should not escalate high-confidence failures")

    res = triage_failures(failures, judge_fn=judge)
    assert res.llm_calls == 0
    assert res.escalated_clusters == 0
    assert res.final_counts.get(ENVIRONMENT) == 1
    assert res.final_counts.get(SNAPSHOT_DRIFT) == 1


def test_low_confidence_cluster_judged_once_and_propagated():
    # three failures share one root cause (KeyError: 'plan_pool') -> one cluster, one model call
    failures = [("t1", "KeyError: 'plan_pool'"),
                ("t2", "KeyError: 'plan_pool'"),
                ("t3", "KeyError: 'plan_pool'")]
    calls = {"n": 0}

    def judge(reason, test_id):
        calls["n"] += 1
        return ENVIRONMENT  # pretend the model reclassifies this cluster

    res = triage_failures(failures, judge_fn=judge)
    assert calls["n"] == 1            # judged ONE representative
    assert res.llm_calls == 1
    assert res.clusters == 1
    assert res.propagated_clusters == 1
    # propagated to all three members
    assert all(r["category"] == ENVIRONMENT for r in res.final)
    assert all(r["source"] == "llm_cluster" for r in res.final)
    assert len(res.reclassified) == 3   # each member moved off the deterministic label


def test_finer_propagation_key_separates_distinct_keys():
    # same masked signature (KeyError: X) but DIFFERENT keys -> must NOT share a cluster
    failures = [("t1", "KeyError: 'plan_pool'"), ("t2", "KeyError: 'other_key'")]
    res = triage_failures(failures, judge_fn=lambda r, t: GENUINELY_BROKEN)
    assert res.clusters == 2            # finer key keeps them apart


def test_contested_cluster_falls_back_to_per_item():
    # two members share a propagation key but the model gives DIFFERENT verdicts on the samples
    failures = [("t1", "AssertionError: boom"), ("t2", "AssertionError: boom"),
                ("t3", "AssertionError: boom")]
    seq = iter([ENVIRONMENT, GENUINELY_BROKEN])  # first two samples disagree

    def judge(reason, test_id):
        try:
            return next(seq)
        except StopIteration:
            return GENUINELY_BROKEN

    res = triage_failures(failures, judge_fn=judge, samples_per_cluster=2)
    assert res.contested_clusters == 1
    assert res.propagated_clusters == 0
    assert res.llm_calls == 3           # 2 samples + 1 remaining member, all judged individually
    assert all(r["source"] == "llm_direct" for r in res.final)


def test_full_mode_judges_every_item():
    failures = [("t1", "KeyError: 'plan_pool'"), ("t2", "KeyError: 'plan_pool'")]
    calls = {"n": 0}

    def judge(reason, test_id):
        calls["n"] += 1
        return GENUINELY_BROKEN

    res = triage_failures(failures, judge_fn=judge, full=True)
    assert calls["n"] == 2             # no propagation; every item judged
    assert all(r["source"] == "llm_direct" for r in res.final)


def test_distinct_root_causes_form_distinct_clusters():
    failures = [("t1", "KeyError: 'plan_pool'"),
                ("t2", "IndexError: list index out of range"),
                ("t3", "ValueError: low quality acknowledgment is required")]

    def judge(reason, test_id):
        return GENUINELY_BROKEN

    res = triage_failures(failures, judge_fn=judge)
    assert res.clusters == 3
    assert res.llm_calls == 3


def test_judge_none_is_deterministic_dry_run():
    failures = [("t1", "KeyError: 'plan_pool'"), ("t2", "KeyError: 'plan_pool'")]
    res = triage_failures(failures, judge_fn=None)
    assert res.llm_calls == 0
    assert res.escalated_clusters == 1   # would escalate one cluster
    # categories stay at the deterministic label when no judge is supplied
    assert all(r["category"] == GENUINELY_BROKEN for r in res.final)


def test_estimate_cost_reports_reduction():
    failures = [("t%d" % i, "KeyError: 'plan_pool'") for i in range(80)]
    failures += [("e%d" % i, "ConnectionRefusedError: refused") for i in range(20)]
    est = estimate_cost(failures, secs_per_call=5.0)
    assert est["failures"] == 100
    # 80 share one cluster, the 20 env are high-confidence (not escalated) -> 1 routed call
    assert est["routed_llm_calls"] == 1
    assert est["naive_llm_calls"] == 100
    assert est["eligible_items"] == 80      # full mode would judge all 80 low-confidence items
    assert est["full_llm_calls"] == 80
    assert est["reduction_x"] == 100.0
    assert est["routed_secs"] == 5.0
