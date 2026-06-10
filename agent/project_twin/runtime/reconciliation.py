"""Static/runtime reconciliation v2 and truthful rollup (PI-8).

Reconciles an inferred static/behavioral fact against runtime observations and produces a
truthful decision: confirm, partially_confirm, contradict, not_observed, unavailable, or
stale. A verified status requires a matching source revision; stale observations never
verify new source. Contradicted facts are retained historically. The rollup keeps
``unavailable`` explicit everywhere and a collector failure can never become task success.
"""

from __future__ import annotations

from typing import Iterable

from pydantic import Field

from agent.project_intelligence.contracts import (
    RuntimeObservationRecord,
    _Frozen,
)

# Decisions.
CONFIRM = "confirm"
PARTIALLY_CONFIRM = "partially_confirm"
CONTRADICT = "contradict"
NOT_OBSERVED = "not_observed"
UNAVAILABLE = "unavailable"
STALE = "stale"

# Statuses (runtime view; never overwrites the canonical inferred record).
VERIFIED = "verified"
INFERRED = "inferred"
CONTRADICTED = "contradicted"


class ReconciledOutcome(_Frozen):
    fact_ref: str
    decision: str
    status: str
    source_revision: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)  # prior statuses retained
    diagnostics: list[str] = Field(default_factory=list)


def reconcile(
    fact_ref: str,
    observations: Iterable[RuntimeObservationRecord],
    *,
    current_source_revision: str | None,
    prior_status: str = INFERRED,
    expect_passed: bool = True,
) -> ReconciledOutcome:
    """Reconcile one fact against observations whose subject_refs include ``fact_ref``."""
    relevant = [o for o in observations if fact_ref in o.subject_refs]
    history = [prior_status]

    if not relevant:
        return ReconciledOutcome(fact_ref=fact_ref, decision=NOT_OBSERVED, status=prior_status,
                                 source_revision=current_source_revision, history=history,
                                 diagnostics=["no runtime observation for fact"])

    # Unavailable dominates: if any relevant observation is unavailable and none passed at the
    # current revision, the fact remains unverified and explicitly unavailable.
    fresh = [o for o in relevant if o.source_revision == current_source_revision]
    stale = [o for o in relevant if o.source_revision != current_source_revision]

    passed_fresh = [o for o in fresh if o.result == "passed"]
    failed_fresh = [o for o in fresh if o.result == "failed"]
    unavailable_fresh = [o for o in fresh if o.result == "unavailable"]

    if failed_fresh:
        # Runtime contradicts the inferred fact; retain prior status historically.
        return ReconciledOutcome(
            fact_ref=fact_ref, decision=CONTRADICT, status=CONTRADICTED,
            source_revision=current_source_revision,
            evidence_refs=[o.observation_id for o in failed_fresh],
            history=history + [CONTRADICTED],
            diagnostics=["runtime observation failed; static assumption contradicted"],
        )
    if passed_fresh and expect_passed:
        observed_subjects = set().union(*[set(o.subject_refs) for o in passed_fresh])
        partial = fact_ref in observed_subjects and len(observed_subjects) > 1
        decision = PARTIALLY_CONFIRM if partial else CONFIRM
        return ReconciledOutcome(
            fact_ref=fact_ref, decision=decision, status=VERIFIED,
            source_revision=current_source_revision,
            evidence_refs=[o.observation_id for o in passed_fresh],
            history=history + [VERIFIED],
        )
    if unavailable_fresh:
        return ReconciledOutcome(
            fact_ref=fact_ref, decision=UNAVAILABLE, status=prior_status,
            source_revision=current_source_revision,
            evidence_refs=[o.observation_id for o in unavailable_fresh],
            history=history, diagnostics=["instrumentation unavailable; not verified"],
        )
    if stale:
        # Only stale observations exist: cannot verify the current source revision.
        return ReconciledOutcome(
            fact_ref=fact_ref, decision=STALE, status=prior_status,
            source_revision=current_source_revision,
            evidence_refs=[o.observation_id for o in stale],
            history=history,
            diagnostics=["only stale observations; new source revision not verified"],
        )
    return ReconciledOutcome(fact_ref=fact_ref, decision=NOT_OBSERVED, status=prior_status,
                             source_revision=current_source_revision, history=history)


class RollupResult(_Frozen):
    success: bool
    passed: int = 0
    failed: int = 0
    observed: int = 0
    unavailable: int = 0
    diagnostics: list[str] = Field(default_factory=list)


def summarize_rollup(observations: Iterable[RuntimeObservationRecord]) -> RollupResult:
    """Truthful rollup: success requires >=1 passed, zero failed, and zero unavailable.

    Unavailable is preserved in the counts and forces success=False — it is never silently
    treated as passed, in the UI or the final rollup.
    """
    obs = list(observations)
    passed = sum(1 for o in obs if o.result == "passed")
    failed = sum(1 for o in obs if o.result == "failed")
    observed = sum(1 for o in obs if o.result == "observed")
    unavailable = sum(1 for o in obs if o.result == "unavailable")
    diagnostics: list[str] = []
    if unavailable:
        diagnostics.append(f"{unavailable} unavailable observation(s) — cannot claim success")
    if failed:
        diagnostics.append(f"{failed} failed observation(s)")
    success = passed > 0 and failed == 0 and unavailable == 0
    return RollupResult(success=success, passed=passed, failed=failed, observed=observed,
                        unavailable=unavailable, diagnostics=diagnostics)
