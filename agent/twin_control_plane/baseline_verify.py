"""Baseline-comparison verification for the autonomous loop.

A repo under active development has many pre-existing test failures (KasaneCore: ~559). So "run the
tests and see a failure" cannot decide whether a change is safe — the failure may have been there
already. This compares the failures AFTER a change to the BASELINE before it and keeps only the DELTA:
a test that passed before and fails now is a NEW failure the change introduced; a pre-existing failure
is not the change's fault. The change broke functionality iff it introduced a new failure.

It is deterministic. It also names the cases a machine CANNOT decide on its own, so the loop can handle
them explicitly (a weak LLM is allowed only for these):

- FLAKY: a new failure that passes on re-run — not a real break (mitigated here by re-run).
- UNVERIFIABLE: the change touched source symbols with NO covering test — there is no test that can
  confirm it; mechanical verification is blind here (needs a generated test, or review).
- AMBIGUOUS_STALE: a new failure that may be a STALE test asserting a contract the change intentionally
  changed (the plan_pool case), not a real break — telling these apart needs code context (the
  weak-LLM failure_judge), so it is flagged AMBIGUOUS rather than auto-failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

PASS = "pass"            # no new failures — safe to keep
FAIL = "fail"            # new failures introduced — roll back
AMBIGUOUS = "ambiguous"  # new failures, but they might be stale tests / need judgment
UNVERIFIABLE = "unverifiable"  # the change touched code with no test coverage


@dataclass
class VerificationVerdict:
    decision: str
    new_failures: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    still_failing: list[str] = field(default_factory=list)
    flaky: list[str] = field(default_factory=list)
    uncovered_symbols: list[str] = field(default_factory=list)
    reason: str = ""


def _norm(values: Iterable[str]) -> set[str]:
    return {str(v).strip() for v in values if str(v).strip()}


def evaluate_verification(
    baseline_failures: Iterable[str],
    after_failures: Iterable[str],
    *,
    flaky: Iterable[str] = (),
    uncovered_symbols: Iterable[str] = (),
    stale_suspect: Iterable[str] = (),
) -> VerificationVerdict:
    """Decide keep/rollback from the failure DELTA.

    ``baseline_failures`` / ``after_failures``: failing test ids before / after the change.
    ``flaky``: new failures already shown flaky on re-run (excluded from "new"). ``uncovered_symbols``:
    changed symbols with no covering test (UNVERIFIABLE if there is otherwise nothing to check).
    ``stale_suspect``: new-failure test ids a context check thinks are stale, not breaks -> AMBIGUOUS."""
    base = _norm(baseline_failures)
    after = _norm(after_failures)
    flaky_set = _norm(flaky)
    uncovered = sorted(_norm(uncovered_symbols))
    stale = _norm(stale_suspect)

    new = sorted((after - base) - flaky_set)
    fixed = sorted(base - after)
    still = sorted(base & after)

    if not new:
        # No new failures. If the change touched only UNCOVERED code, there was nothing to verify.
        if uncovered:
            return VerificationVerdict(UNVERIFIABLE, [], fixed, still, sorted(flaky_set), uncovered,
                                       reason="no new failures, but changed symbols have no covering test")
        return VerificationVerdict(PASS, [], fixed, still, sorted(flaky_set), uncovered,
                                   reason="no new failures introduced")

    # New failures exist. If every new failure is a suspected STALE test, it is ambiguous, not a break.
    if stale and set(new) <= stale:
        return VerificationVerdict(AMBIGUOUS, new, fixed, still, sorted(flaky_set), uncovered,
                                   reason="new failures are all suspected stale tests; needs a context judgment")
    return VerificationVerdict(FAIL, new, fixed, still, sorted(flaky_set), uncovered,
                               reason=f"{len(new)} new failure(s) introduced by the change")


def run_baseline_verification(run_tests_fn, impacted_tests, baseline_failures, *, flaky_reruns: int = 1,
                              uncovered_symbols: Iterable[str] = (), stale_suspect: Iterable[str] = ()):
    """Run the IMPACTED tests, re-run any new failures to filter flakiness, and evaluate against the
    baseline. ``run_tests_fn(test_ids) -> set[failing_test_id]``. Deterministic; the weak LLM is only
    needed to populate ``stale_suspect`` for an AMBIGUOUS verdict."""
    impacted = list(_norm(impacted_tests))
    after = _norm(run_tests_fn(impacted)) if impacted else set()
    base = _norm(baseline_failures)
    new = (after - base)
    flaky: set[str] = set()
    for _ in range(max(0, flaky_reruns)):
        if not new:
            break
        rerun_failing = _norm(run_tests_fn(sorted(new)))
        passed_on_rerun = new - rerun_failing
        flaky |= passed_on_rerun
        new = new & rerun_failing
    return evaluate_verification(base, after, flaky=flaky, uncovered_symbols=uncovered_symbols,
                                 stale_suspect=stale_suspect)
