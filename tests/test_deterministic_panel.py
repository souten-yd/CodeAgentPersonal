"""Tests for the multi-perspective deterministic classification panel (no real model)."""
from __future__ import annotations

from agent.twin_control_plane.deterministic_panel import (
    ENVIRONMENT, GENUINELY_BROKEN, SNAPSHOT_DRIFT,
    classify_with_panel, exception_prior, infra_prior, judge_with_focus, marker_prior,
    structure_prior, triage_with_panel,
)


def test_marker_prior_abstains_without_a_marker():
    assert marker_prior("AssertionError: assert 1 == 2") is None     # no marker -> abstain (not broken)
    assert marker_prior("ConnectionRefusedError: refused") == ENVIRONMENT


def test_exception_prior_reads_the_leading_class():
    assert exception_prior("FileNotFoundError: no such file") == ENVIRONMENT
    assert exception_prior("KeyError: 'plan_pool'") == GENUINELY_BROKEN
    assert exception_prior("DeprecationWarning: x is deprecated") != GENUINELY_BROKEN
    assert exception_prior("assert 1 == 2") is None                  # bare pytest rewrite -> abstain


def test_structure_prior_reads_assert_target():
    assert structure_prior("assert 'x' in '<!DOCTYPE html>\\n<html>'") == SNAPSHOT_DRIFT
    assert structure_prior("assert 'asset ready\\r\\n' == 'asset ready\\n'") == ENVIRONMENT
    assert structure_prior("KeyError: 'plan_pool'") is None


def test_infra_prior_flags_harness_failures():
    assert infra_prior("failed on setup with \"worker 'gw3' crashed\"") == ENVIRONMENT
    assert infra_prior("collection failure") == ENVIRONMENT
    assert infra_prior("KeyError: 'plan_pool'") is None


def test_unanimous_priors_settle_without_escalation():
    # FileNotFoundError: marker=env, exception=env, structure abstains, infra abstains -> unanimous env
    pc = classify_with_panel("FileNotFoundError: web/atlas-next/x.vue not found")
    assert pc.category == ENVIRONMENT
    assert pc.agree is True and pc.escalate is False
    assert pc.confidence == 1.0


def test_html_body_false_positive_is_no_longer_environment():
    # The exact failure mode the single classifier got wrong: an env-ish substring ("timeout") inside a
    # rendered HTML body. Because env/infra markers now read only the assertion INTENT (before "in '..."),
    # the body's "timeout" no longer fires ENVIRONMENT — structure (snapshot) vs exception (broken)
    # remain, so it correctly ESCALATES instead of being silently mislabeled environment.
    reason = "AssertionError: 'Guided Plan Flow' not found in '<!DOCTYPE html>\\n<html>... timeout ...'"
    pc = classify_with_panel(reason)
    assert pc.escalate is True
    assert ENVIRONMENT not in pc.votes.values()      # the false positive is gone
    assert SNAPSHOT_DRIFT in pc.votes.values()


def test_triage_settles_bulk_and_escalates_residual():
    failures = [
        ("t1", "FileNotFoundError: x.vue"),                 # unanimous env -> settled
        ("t2", "KeyError: 'plan_pool'"),                    # exception=broken, others abstain -> settled
        ("t3", "AssertionError: 'a' not found in '<!DOCTYPE html> timeout'"),  # split -> escalate
    ]
    judged = {"n": 0, "focus": None}

    def judge(reason, test_id, focus):
        judged["n"] += 1
        judged["focus"] = focus
        return SNAPSHOT_DRIFT

    res = triage_with_panel(failures, judge_fn=judge)
    assert res.total == 3
    assert res.settled == 2
    assert res.escalated == 1
    assert res.clusters == 1 and res.llm_calls == 1
    assert judged["n"] == 1
    # the judge was handed the competing labels (focus) to adjudicate
    assert SNAPSHOT_DRIFT in judged["focus"] and GENUINELY_BROKEN in judged["focus"]
    # the escalated record took the judge's verdict
    escalated = [r for r in res.final if r["source"] == "llm_cluster"]
    assert escalated and escalated[0]["category"] == SNAPSHOT_DRIFT


def test_judge_with_focus_picks_among_candidates_only():
    # the model tries to answer outside focus -> rejected, falls back to first focus label
    def llm_outside(system, user):
        return {"category": "test_debt"}

    assert judge_with_focus(llm_outside, "x", [SNAPSHOT_DRIFT, GENUINELY_BROKEN]) == SNAPSHOT_DRIFT

    def llm_valid(system, user):
        return {"category": "genuinely_broken"}

    assert judge_with_focus(llm_valid, "x", [SNAPSHOT_DRIFT, GENUINELY_BROKEN]) == GENUINELY_BROKEN

    # single-candidate focus short-circuits without calling the model
    def llm_boom(system, user):
        raise AssertionError("must not be called for a single-candidate focus")

    assert judge_with_focus(llm_boom, "x", [ENVIRONMENT]) == ENVIRONMENT


def test_triage_dry_run_keeps_panel_best_guess():
    failures = [("t3", "AssertionError: 'a' not found in '<!DOCTYPE html> timeout'")]
    res = triage_with_panel(failures, judge_fn=None)
    assert res.llm_calls == 0
    assert res.escalated == 1
    # with no judge the split record keeps the majority best-guess label (one of the voted buckets)
    assert res.final[0]["category"] in (ENVIRONMENT, SNAPSHOT_DRIFT, GENUINELY_BROKEN)
