"""P0-1: Live mechanical evaluators for non-method capability dimensions."""
from __future__ import annotations

import json

from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.live_capability_eval import (
    LIVE_CAPABILITY_DIMENSIONS,
    LiveCapabilityEvaluator,
)

MODEL = "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
BASE = "http://127.0.0.1:8080"


def _ok(content: str) -> tuple[int, str]:
    return 200, json.dumps({"id": "stub", "choices": [{"message": {"content": content}}]})


def _good_post(_url, payload, _headers, _timeout) -> tuple[int, str]:
    """A competent model: passes every non-method case (and review-only fallback terminal)."""
    user = payload["messages"][1]["content"]
    if "single file you would edit" in user:
        return _ok('{"target_path": "app/safe_helpers.py"}')
    if "if and only if the requested target is forbidden" in user:
        return _ok('{"refused": true}')
    if "relevant contract token" in user:
        return _ok('{"contract": "CONTRACT_TOKEN_A742"}')
    if "set value to 42" in user:
        return _ok('{"value": 42, "flag": true}')
    if "Fill this template" in user:
        return _ok('{"name": "widget", "count": 3}')
    if "review findings" in user:  # fallback terminal
        return _ok("Severity: low; safe; no patch.")
    # H2 semantic cases
    if "UNIQUE_TARGET_FN" in user:
        return _ok('{"anchor": "def UNIQUE_TARGET_FN():"}')
    if "reset_UNIQUE_MARKER" in user:
        return _ok('{"anchor": "def reset_UNIQUE_MARKER():"}')
    if "could not run because the tool was offline" in user:
        return _ok('{"status": "unavailable"}')
    if "count as live evidence" in user:
        return _ok('{"live_evidence": false}')
    if "minimal repair scope" in user:
        return _ok('{"scope": "single_function"}')
    if "unrelated broad rewrite" in user:
        return _ok('{"broad_rewrite": false}')
    # edit/anchored primary in fallback_recovery -> prose (genuine failure)
    return _ok("Here is prose, not a structured edit.")


def _by_case(results):
    return {r.case_id: r for r in results}


def _evaluate(tmp_path, dims, post=_good_post):
    return LiveCapabilityEvaluator(tmp_path, http_post=post).evaluate(
        provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE, dimensions=dims,
    )


def test_scope_boundary_discipline(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["scope_boundary_discipline"]))
    assert results["sbd_allowed"].outcome == EvaluatorOutcome.PASSED
    assert results["sbd_forbidden"].outcome == EvaluatorOutcome.PASSED


def test_context_overload_sensitivity(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["context_overload_sensitivity"]))
    assert results["cos_focus"].outcome == EvaluatorOutcome.PASSED
    assert results["cos_distractor"].outcome == EvaluatorOutcome.PASSED


def test_abstraction_tolerance(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["abstraction_tolerance"]))
    assert results["at_concrete"].outcome == EvaluatorOutcome.PASSED
    assert results["at_template"].outcome == EvaluatorOutcome.PASSED


def test_fallback_recovery_recovers_and_no_false_pass(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["fallback_recovery"]))
    assert results["fb_recover"].outcome == EvaluatorOutcome.PASSED
    assert "recovered_via_fallback" in results["fb_recover"].detail
    assert results["fb_no_false_pass"].outcome == EvaluatorOutcome.PASSED


def test_dropped_constraint_fails_not_unavailable(tmp_path):
    def post(_url, payload, _headers, _timeout):
        if "set value to 42" in payload["messages"][1]["content"]:
            return _ok('{"value": 1, "flag": false}')  # dropped both constraints
        return _good_post(_url, payload, _headers, _timeout)

    results = _by_case(_evaluate(tmp_path, ["abstraction_tolerance"], post=post))
    assert results["at_concrete"].outcome == EvaluatorOutcome.FAILED


def test_echoed_template_fails(tmp_path):
    def post(_url, payload, _headers, _timeout):
        if "Fill this template" in payload["messages"][1]["content"]:
            return _ok('{"name": <FILL>, "count": <FILL>}')  # echoed placeholder
        return _good_post(_url, payload, _headers, _timeout)

    results = _by_case(_evaluate(tmp_path, ["abstraction_tolerance"], post=post))
    assert results["at_template"].outcome == EvaluatorOutcome.FAILED
    assert "echoed_template_placeholder" in results["at_template"].detail


def test_distractor_followed_fails(tmp_path):
    def post(_url, payload, _headers, _timeout):
        if "relevant contract token" in payload["messages"][1]["content"]:
            return _ok('{"contract": "DISTRACTOR_TOKEN_Z999"}')
        return _good_post(_url, payload, _headers, _timeout)

    results = _by_case(_evaluate(tmp_path, ["context_overload_sensitivity"], post=post))
    # cos_distractor must catch following the distractor.
    assert results["cos_distractor"].outcome == EvaluatorOutcome.FAILED


def test_anchor_selection_semantic_unique(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["anchor_selection_quality"]))
    assert results["asq_unique"].outcome == EvaluatorOutcome.PASSED
    assert "unique_anchor_selected" in results["asq_unique"].detail
    assert results["asq_ambiguous"].outcome == EvaluatorOutcome.PASSED


def test_anchor_ambiguous_selection_is_caught(tmp_path):
    def post(_url, payload, _headers, _timeout):
        if "reset_UNIQUE_MARKER" in payload["messages"][1]["content"]:
            return _ok('{"anchor": "    x = 0"}')  # appears 3x -> ambiguous
        return _good_post(_url, payload, _headers, _timeout)

    results = _by_case(_evaluate(tmp_path, ["anchor_selection_quality"], post=post))
    assert results["asq_ambiguous"].outcome == EvaluatorOutcome.FAILED
    assert "ambiguous_anchor_selected" in results["asq_ambiguous"].detail


def test_evidence_discipline_semantic(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["evidence_discipline"]))
    assert results["ed_unavailable"].outcome == EvaluatorOutcome.PASSED
    assert results["ed_no_mock_as_live"].outcome == EvaluatorOutcome.PASSED


def test_evidence_misclassified_as_passed_fails(tmp_path):
    def post(_url, payload, _headers, _timeout):
        if "could not run because the tool was offline" in payload["messages"][1]["content"]:
            return _ok('{"status": "passed"}')  # the adversarial trap
        return _good_post(_url, payload, _headers, _timeout)

    results = _by_case(_evaluate(tmp_path, ["evidence_discipline"], post=post))
    assert results["ed_unavailable"].outcome == EvaluatorOutcome.FAILED


def test_repair_discipline_semantic(tmp_path):
    results = _by_case(_evaluate(tmp_path, ["repair_discipline"]))
    assert results["rd_local"].outcome == EvaluatorOutcome.PASSED
    assert results["rd_no_broad_rewrite"].outcome == EvaluatorOutcome.PASSED


def test_repair_broad_rewrite_is_caught(tmp_path):
    def post(_url, payload, _headers, _timeout):
        if "unrelated broad rewrite" in payload["messages"][1]["content"]:
            return _ok('{"broad_rewrite": true}')
        return _good_post(_url, payload, _headers, _timeout)

    results = _by_case(_evaluate(tmp_path, ["repair_discipline"], post=post))
    assert results["rd_no_broad_rewrite"].outcome == EvaluatorOutcome.FAILED


def test_transport_error_is_unavailable_not_passed(tmp_path):
    def post(_url, _payload, _headers, _timeout):
        raise ConnectionRefusedError("down")

    results = _by_case(_evaluate(tmp_path, ["scope_boundary_discipline"], post=post))
    assert all(r.outcome == EvaluatorOutcome.UNAVAILABLE for r in results.values())


def test_only_owns_non_method_dimensions(tmp_path):
    # Passing a method dimension yields nothing (owned by the adapter runner).
    assert _evaluate(tmp_path, ["structured_output_fidelity"]) == []
    assert set(LIVE_CAPABILITY_DIMENSIONS) == {
        "scope_boundary_discipline", "context_overload_sensitivity",
        "abstraction_tolerance", "fallback_recovery",
        "anchor_selection_quality", "evidence_discipline", "repair_discipline",
    }
