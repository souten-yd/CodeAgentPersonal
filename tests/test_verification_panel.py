"""Deterministic tests for the multi-perspective verification panel.

Genuine negative controls: each perspective is shown to BOTH pass and fail the aggregate, so a
regression that turns a perspective into a no-op (always 1.0) would break a test here.
"""
from __future__ import annotations

from agent.twin_control_plane.baseline_verify import VerificationVerdict, PASS, FAIL, AMBIGUOUS, UNVERIFIABLE
from agent.twin_control_plane.verification_panel import (
    ACCEPT, REJECT, REVIEW, Perspective, aggregate, evaluate_change, reference_perspective,
    semantic_perspective, syntax_perspective,
)

_OK = {"agent/m.py": "def f():\n    return 1\n"}
_BAD = {"agent/m.py": "def f(:\n    return 1\n"}  # syntax error


def _pass_verdict():
    return VerificationVerdict(PASS, reason="no new failures")


def _fail_verdict():
    return VerificationVerdict(FAIL, new_failures=["t_x"], reason="1 new failure")


# --- syntax perspective (gating) ---

def test_syntax_gate_rejects_unparseable_change():
    v = evaluate_change(_BAD, _pass_verdict())
    assert v.decision == REJECT
    assert v.gate_failed == "syntax"


def test_syntax_ok_does_not_reject():
    v = evaluate_change(_OK, _pass_verdict())
    assert v.decision == ACCEPT


def test_syntax_short_circuits_before_semantic():
    # even with a PASSING semantic verdict, a syntax error wins (gate short-circuit)
    v = evaluate_change(_BAD, _pass_verdict())
    assert v.decision == REJECT and v.gate_failed == "syntax"


# --- semantic perspective ---

def test_semantic_fail_drives_reject():
    v = evaluate_change(_OK, _fail_verdict())
    assert v.decision == REJECT
    assert v.confidence < 0.5


def test_semantic_ambiguous_drives_review():
    v = evaluate_change(_OK, VerificationVerdict(AMBIGUOUS, new_failures=["t_stale"]))
    assert v.decision == REVIEW


def test_semantic_unverifiable_abstains_and_with_clean_syntax_is_accept():
    # syntax=1.0, semantic abstains -> only syntax scores -> ACCEPT (nothing contradicts it)
    v = evaluate_change(_OK, VerificationVerdict(UNVERIFIABLE, uncovered_symbols=["py://m.py#f"]))
    assert v.decision == ACCEPT
    assert "semantic" in v.abstained


# --- reference perspective ---

def test_reference_flags_invented_symbol():
    content = {"agent/x.py": "from agent.realmod import nope\n"}
    p = reference_perspective(content, modules={"agent.realmod"},
                              module_symbols={"agent.realmod:real"})
    assert p.score == 0.0
    assert p.findings


def test_reference_resolves_real_symbol():
    content = {"agent/x.py": "from agent.realmod import real\n"}
    p = reference_perspective(content, modules={"agent.realmod"},
                              module_symbols={"agent.realmod:real"})
    assert p.score == 1.0


def test_reference_abstains_with_no_project_import():
    content = {"agent/x.py": "import os\n"}
    p = reference_perspective(content, modules={"agent.realmod"}, module_symbols=set())
    assert p.score is None


def test_invented_reference_lowers_score_to_review_or_reject():
    content = {"agent/x.py": "from agent.realmod import nope\ndef f():\n    return 1\n"}
    v = evaluate_change(content, _pass_verdict(), modules={"agent.realmod"},
                        module_symbols={"agent.realmod:real"})
    # syntax 1.0(w1) + reference 0.0(w2) + semantic 1.0(w3) = (1+0+3)/6 = 0.67 -> REVIEW
    assert v.decision == REVIEW
    assert v.confidence < 1.0


# --- aggregate edge cases ---

def test_all_abstain_is_review():
    v = aggregate([Perspective("a", None), Perspective("b", None)])
    assert v.decision == REVIEW


def test_gate_threshold_only_applies_to_gating_perspectives():
    # a NON-gating perspective at 0.0 is averaged, not a hard gate
    v = aggregate([Perspective("syntax", 1.0, weight=1.0, gating=True),
                   Perspective("semantic", 0.0, weight=3.0)])
    assert v.gate_failed == ""
    assert v.decision == REJECT  # by score, not by gate
