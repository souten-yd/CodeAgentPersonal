"""Deterministic tests for baseline-comparison verification.

These have genuine negative controls: a change that introduces a NEW failure must FAIL, a change that
introduces none must PASS, and the ambiguous/unverifiable cases are asserted explicitly so a regression
that collapses the verdict to a single value would break here.
"""
from __future__ import annotations

from agent.twin_control_plane.baseline_verify import (
    AMBIGUOUS, FAIL, PASS, UNVERIFIABLE, evaluate_verification, run_baseline_verification,
)


def test_new_failure_fails():
    v = evaluate_verification(["t_a", "t_b"], ["t_a", "t_b", "t_c"])
    assert v.decision == FAIL
    assert v.new_failures == ["t_c"]
    assert v.still_failing == ["t_a", "t_b"]


def test_no_new_failure_passes():
    v = evaluate_verification(["t_a", "t_b"], ["t_a"])
    assert v.decision == PASS
    assert v.new_failures == []
    assert v.fixed == ["t_b"]  # a pre-existing failure that now passes is reported as fixed


def test_identical_baseline_and_after_passes():
    v = evaluate_verification(["t_a", "t_b"], ["t_b", "t_a"])
    assert v.decision == PASS
    assert v.new_failures == []


def test_all_new_failures_stale_is_ambiguous():
    v = evaluate_verification(["t_a"], ["t_a", "t_stale"], stale_suspect=["t_stale"])
    assert v.decision == AMBIGUOUS
    assert v.new_failures == ["t_stale"]


def test_mixed_stale_and_real_new_failure_still_fails():
    # one new failure is a suspected stale test, the other is not -> not purely stale -> FAIL
    v = evaluate_verification(["t_a"], ["t_a", "t_stale", "t_real"], stale_suspect=["t_stale"])
    assert v.decision == FAIL
    assert v.new_failures == ["t_real", "t_stale"]


def test_uncovered_change_is_unverifiable():
    v = evaluate_verification(["t_a"], ["t_a"], uncovered_symbols=["py://m.py#f"])
    assert v.decision == UNVERIFIABLE
    assert v.uncovered_symbols == ["py://m.py#f"]


def test_uncovered_ignored_when_a_new_failure_exists():
    # a real new failure dominates: we have a concrete break, so it is FAIL not UNVERIFIABLE
    v = evaluate_verification(["t_a"], ["t_a", "t_c"], uncovered_symbols=["py://m.py#f"])
    assert v.decision == FAIL


def test_flaky_new_failure_excluded():
    v = evaluate_verification(["t_a"], ["t_a", "t_flaky"], flaky=["t_flaky"])
    assert v.decision == PASS
    assert v.flaky == ["t_flaky"]


def test_run_baseline_verification_filters_flaky_on_rerun():
    calls = {"n": 0}

    def run_tests(test_ids):
        calls["n"] += 1
        if calls["n"] == 1:
            # first impacted-test run: t_flaky fails
            return {"t_flaky"}
        # re-run of new failures: t_flaky passes this time -> flaky, not a real break
        return set()

    v = run_baseline_verification(run_tests, ["t_flaky", "t_x"], baseline_failures=[], flaky_reruns=1)
    assert v.decision == PASS
    assert v.flaky == ["t_flaky"]


def test_run_baseline_verification_real_new_failure_fails():
    def run_tests(test_ids):
        # consistently fails on both the impacted run and the re-run -> real break
        return {"t_broken"}

    v = run_baseline_verification(run_tests, ["t_broken"], baseline_failures=[], flaky_reruns=1)
    assert v.decision == FAIL
    assert v.new_failures == ["t_broken"]


def test_run_baseline_verification_no_impacted_tests_is_unverifiable_when_uncovered():
    def run_tests(test_ids):  # pragma: no cover - should not be called with empty impacted set
        raise AssertionError("run_tests should not be called when there are no impacted tests")

    v = run_baseline_verification(run_tests, [], baseline_failures=[],
                                  uncovered_symbols=["py://m.py#f"])
    assert v.decision == UNVERIFIABLE
