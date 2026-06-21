from __future__ import annotations

from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.eval_packs import (
    CAPABILITY_DIMENSIONS,
    CaseResult,
    load_eval_packs,
    pack_for_dimension,
    score_pack,
)


METHOD_DIMENSIONS = {
    "structured_output_fidelity",
    "patch_protocol_fidelity",
    "edit_intent_quality",
    "anchor_selection_quality",
    "abstraction_tolerance",
    "fallback_recovery",
    "scope_boundary_discipline",
    "context_overload_sensitivity",
}


def test_method_dimensions_have_complete_eval_packs():
    assert METHOD_DIMENSIONS.issubset(CAPABILITY_DIMENSIONS)
    packs = {pack.dimension: pack for pack in load_eval_packs()}
    for dimension in METHOD_DIMENSIONS:
        pack = packs[dimension]
        assert pack.cases
        assert all(case.dimension == dimension for case in pack.cases)
        assert any(case.adversarial for case in pack.cases)


def test_method_adversarial_case_has_double_weight():
    pack = pack_for_dimension("fallback_recovery")
    results = [
        CaseResult(
            case_id="fb_recover",
            dimension="fallback_recovery",
            outcome=EvaluatorOutcome.PASSED,
        ),
        CaseResult(
            case_id="fb_no_false_pass",
            dimension="fallback_recovery",
            outcome=EvaluatorOutcome.FAILED,
        ),
    ]
    score = score_pack(pack, results)
    assert score.score == 0.3333
    assert score.outcome == EvaluatorOutcome.FAILED


def test_unavailable_method_cases_never_become_zero_or_passed():
    pack = pack_for_dimension("structured_output_fidelity")
    score = score_pack(pack, [
        CaseResult(
            case_id=case.case_id,
            dimension=pack.dimension,
            outcome=EvaluatorOutcome.UNAVAILABLE,
            evidence_refs=[f"evidence/{case.case_id}"],
        )
        for case in pack.cases
    ])
    assert score.score is None
    assert score.outcome == EvaluatorOutcome.UNAVAILABLE
    assert score.sample_count == 0
    assert score.passed == 0
    assert score.unavailable == len(pack.cases)


def test_scope_adversarial_failure_is_not_hidden_by_unavailable_case():
    pack = pack_for_dimension("scope_boundary_discipline")
    score = score_pack(pack, [
        CaseResult(
            case_id="sbd_allowed",
            dimension=pack.dimension,
            outcome=EvaluatorOutcome.UNAVAILABLE,
        ),
        CaseResult(
            case_id="sbd_forbidden",
            dimension=pack.dimension,
            outcome=EvaluatorOutcome.FAILED,
        ),
    ])
    assert score.score == 0.0
    assert score.outcome == EvaluatorOutcome.FAILED
    assert score.sample_count == 1
    assert score.unavailable == 1
