"""PFG-15 — Candidate evaluator foundation tests.

Proves the three invariants: invalid outputs are rejected, unavailable evaluators are
never counted as passed, and no LLM judge is required (the evaluator is pure mechanics).
"""
from __future__ import annotations

from agent.model_forge import (
    VERDICT_ELIGIBLE,
    VERDICT_REJECTED,
    CandidateEvaluationInput,
    CandidateEvaluator,
    EvaluatorOutcome,
    ForgeExecutionResult,
)
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.stage_taxonomy import ForgeStage


def _result(*, contract_valid=True, raw_ref="raw.txt", latency_ms=0, errors=None):
    return ForgeExecutionResult(
        request_id="r1", provider_id="local", model_id="m1",
        route_id=ForgeRoute.DIRECT_PATCH, stage=ForgeStage.PATCH_GENERATION,
        raw_output_ref=raw_ref, contract_valid=contract_valid,
        latency_ms=latency_ms, errors=errors or [],
    )


def test_invalid_contract_is_rejected():
    inp = CandidateEvaluationInput(
        candidate_id="c1",
        execution_result=_result(contract_valid=False, errors=["bad_json"]),
        raw_output="",
    )
    ev = CandidateEvaluator().evaluate(inp)
    assert ev.verdict == VERDICT_REJECTED
    assert ev.score.final_score == 0.0
    assert any("contract_parse" in b for b in ev.score.blocked_reasons)


def test_malformed_json_output_is_rejected():
    inp = CandidateEvaluationInput(
        candidate_id="c2", execution_result=_result(),
        output_contract="json", raw_output="{not valid json",
    )
    ev = CandidateEvaluator().evaluate(inp)
    assert ev.verdict == VERDICT_REJECTED
    assert any("schema_format" in b for b in ev.score.blocked_reasons)


def test_unavailable_evaluators_are_not_passed():
    # Valid output but NO test/runtime/policy evidence supplied at all.
    inp = CandidateEvaluationInput(
        candidate_id="c3", execution_result=_result(),
        output_contract="json", parsed_output={"ok": True},
    )
    ev = CandidateEvaluator().evaluate(inp)
    outcomes = {r.name: r.outcome for r in ev.evaluators}
    # contract + schema pass; everything depending on missing evidence is UNAVAILABLE,
    # never PASSED.
    assert outcomes["contract_parse"] == EvaluatorOutcome.PASSED
    assert outcomes["schema_format"] == EvaluatorOutcome.PASSED
    for name in ("focused_tests", "related_tests", "portal_runtime",
                 "requirement_coverage", "syntax_static", "workspace_policy"):
        assert outcomes[name] == EvaluatorOutcome.UNAVAILABLE, name
    # No unavailable evaluator contributed to the score.
    assert ev.verdict == VERDICT_ELIGIBLE
    assert ev.score.final_score == 1.0  # only the two passing evaluators count


def test_failing_focused_tests_reject():
    inp = CandidateEvaluationInput(
        candidate_id="c4", execution_result=_result(),
        output_contract="json", parsed_output={"ok": True},
        focused_tests_passed=False,
    )
    ev = CandidateEvaluator().evaluate(inp)
    assert ev.verdict == VERDICT_REJECTED
    assert any("focused_tests" in b for b in ev.score.blocked_reasons)


def test_unrelated_file_edit_is_hard_rejected():
    inp = CandidateEvaluationInput(
        candidate_id="c5", execution_result=_result(),
        output_contract="text", raw_output="patch",
        changed_paths=["app/a.py", "secrets/.env"], allowed_paths=["app/a.py"],
    )
    ev = CandidateEvaluator().evaluate(inp)
    assert ev.verdict == VERDICT_REJECTED
    assert any("unrelated_edit" in b for b in ev.score.blocked_reasons)


def test_test_deletion_and_safe_apply_bypass_hard_reject():
    for kwargs in ({"test_deletion_detected": True}, {"bypass_safe_apply_detected": True},
                   {"public_api_changed": True}):
        inp = CandidateEvaluationInput(
            candidate_id="c6", execution_result=_result(),
            output_contract="text", raw_output="x", **kwargs,
        )
        ev = CandidateEvaluator().evaluate(inp)
        assert ev.verdict == VERDICT_REJECTED, kwargs


def test_python_syntax_error_rejected_and_valid_code_passes():
    bad = CandidateEvaluationInput(
        candidate_id="c7", execution_result=_result(),
        output_contract="text", raw_output="code",
        code_artifacts={"m.py": "def f(:\n  pass"}, code_language="python",
    )
    assert CandidateEvaluator().evaluate(bad).verdict == VERDICT_REJECTED

    good = CandidateEvaluationInput(
        candidate_id="c8", execution_result=_result(),
        output_contract="text", raw_output="code",
        code_artifacts={"m.py": "def f():\n    return 1\n"}, code_language="python",
        focused_tests_passed=True,
    )
    ev = CandidateEvaluator().evaluate(good)
    assert ev.verdict == VERDICT_ELIGIBLE
    syntax = next(r for r in ev.evaluators if r.name == "syntax_static")
    assert syntax.outcome == EvaluatorOutcome.PASSED


def test_unknown_language_static_check_is_unavailable_not_passed():
    inp = CandidateEvaluationInput(
        candidate_id="c9", execution_result=_result(),
        output_contract="text", raw_output="code",
        code_artifacts={"m.js": "function(){"}, code_language="javascript",
    )
    ev = CandidateEvaluator().evaluate(inp)
    syntax = next(r for r in ev.evaluators if r.name == "syntax_static")
    assert syntax.outcome == EvaluatorOutcome.UNAVAILABLE
    # An unavailable static check must not let an otherwise-empty candidate "pass" it.
    assert syntax.score == 0.0
