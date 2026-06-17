"""Deterministic tests for the two-pass critique judge (stubbed LLM, no real model).

Negative controls: the critique must be able to OVERTURN the proposal (when it matches the prior) and
must be able to FAIL to overturn it (when it does not), and a three-way disagreement must be marked
contested — so a regression that ignores the critique would break a test here.
"""
from __future__ import annotations

from agent.twin_control_plane.critique_judge import judge_failure_with_critique
from agent.twin_control_plane.failure_classifier import (
    ENVIRONMENT, GENUINELY_BROKEN, SNAPSHOT_DRIFT,
)


def _stub(proposal_category, critic):
    """Build an llm_json_fn that returns ``proposal_category`` for the propose call and ``critic`` for
    the critique call. The propose call (failure_judge) sends a 'category' request; the critique call
    sends an 'agree' request — distinguished by the system prompt."""
    def fn(system, user):
        if system.startswith("You are a skeptical reviewer"):
            return critic
        return {"category": proposal_category}
    return fn


def test_consensus_high_confidence():
    # genuinely_broken reason; proposal agrees, critic agrees -> consensus
    fn = _stub(GENUINELY_BROKEN, {"agree": True})
    r = judge_failure_with_critique(fn, "AssertionError: assert 1 == 2")
    assert r.category == GENUINELY_BROKEN
    assert r.consensus is True
    assert r.confidence >= 0.75


def test_critique_overturns_when_alternative_matches_prior():
    # reason has a CRLF marker -> deterministic prior = ENVIRONMENT.
    # proposal (model) wrongly says genuinely_broken; critic proposes environment (== prior) -> switch.
    reason = "AssertionError: 'asset ready\\r\\n' == 'asset ready\\n'"
    fn = _stub(GENUINELY_BROKEN, {"agree": False, "alternative": "environment"})
    r = judge_failure_with_critique(fn, reason)
    assert r.category == ENVIRONMENT
    assert r.consensus is False
    assert r.confidence == 0.6


def test_critique_dissent_but_proposal_matches_prior_keeps_proposal():
    # CRLF reason -> prior ENVIRONMENT. proposal == environment (matches prior); critic dissents with
    # genuinely_broken (does NOT match prior) -> keep the proposal.
    reason = "AssertionError: 'asset ready\\r\\n' == 'asset ready\\n'"
    fn = _stub(ENVIRONMENT, {"agree": False, "alternative": "genuinely_broken"})
    r = judge_failure_with_critique(fn, reason)
    assert r.category == ENVIRONMENT
    assert r.confidence == 0.6


def test_three_way_disagreement_is_contested():
    # a neutral reason -> prior genuinely_broken. proposal=snapshot_drift, critic=environment.
    # none equals... actually proposal/critic differ from prior -> contested, anchor on prior.
    reason = "some opaque failure with no markers"
    fn = _stub(SNAPSHOT_DRIFT, {"agree": False, "alternative": ENVIRONMENT})
    r = judge_failure_with_critique(fn, reason)
    assert r.contested is True
    assert r.category == GENUINELY_BROKEN  # the deterministic prior anchor
    assert r.confidence == 0.4


def test_critic_no_usable_alternative_keeps_proposal():
    fn = _stub(GENUINELY_BROKEN, {"agree": False, "alternative": "not_a_category"})
    r = judge_failure_with_critique(fn, "AssertionError: assert 1 == 2")
    assert r.category == GENUINELY_BROKEN
    assert r.consensus is True  # no usable alternative -> treated as upheld


def test_model_failure_falls_back_to_prior():
    def boom(system, user):
        raise RuntimeError("model down")
    reason = "AssertionError: 'asset ready\\r\\n' == 'asset ready\\n'"  # prior = environment
    r = judge_failure_with_critique(boom, reason)
    assert r.category == ENVIRONMENT  # deterministic fallback, never raises
