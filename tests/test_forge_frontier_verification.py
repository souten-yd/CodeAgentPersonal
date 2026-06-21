"""PR21: Frontier verification of weak-LLM evaluation results."""
from __future__ import annotations

import json

from agent.model_forge.frontier_verification import (
    FrontierVerificationHarness,
    StaticFrontierJudge,
)

RESULTS = [
    {"dimension": "structured_output_fidelity", "case_id": "sof_schema", "outcome": "passed", "detail": "method_contract_passed"},
    {"dimension": "edit_intent_quality", "case_id": "ei_precise", "outcome": "failed", "detail": "content_missing"},
    {"dimension": "anchor_selection_quality", "case_id": "asq_ambiguous", "outcome": "passed", "detail": "method_contract_passed"},
]


def test_unavailable_when_no_frontier_judge(tmp_path) -> None:
    harness = FrontierVerificationHarness(tmp_path)
    report = harness.verify(run_id="r1", provider_id="p", model_id="m", results=RESULTS)
    assert report["proof_level"] == "frontier_verification_pending"
    assert all(v["assessment"] == "unavailable" for v in report["verdicts"])
    assert report["assessed_cases"] == 0


def test_all_agreements_pass(tmp_path) -> None:
    judge = StaticFrontierJudge({
        "structured_output_fidelity:sof_schema": ("confirms_pass", "valid strict JSON"),
        "edit_intent_quality:ei_precise": ("confirms_fail", "empty anchors are a real failure"),
        "anchor_selection_quality:asq_ambiguous": ("confirms_pass", "anchor genuinely unique"),
    })
    harness = FrontierVerificationHarness(tmp_path, judge=judge)
    report = harness.verify(run_id="r2", provider_id="p", model_id="m", results=RESULTS)
    assert report["proof_level"] == "frontier_verification_passed"
    assert report["agreements"] == 3
    assert report["mismatches"] == []


def test_over_claim_is_mismatch_and_not_upgraded(tmp_path) -> None:
    judge = StaticFrontierJudge({
        "structured_output_fidelity:sof_schema": ("confirms_pass", "valid strict JSON"),
        "edit_intent_quality:ei_precise": ("confirms_fail", "real failure"),
        # Weak said passed, but the case intent (ambiguity avoidance) was never tested.
        "anchor_selection_quality:asq_ambiguous": ("over_claim", "format-only check; ambiguity not verified"),
    })
    harness = FrontierVerificationHarness(tmp_path, judge=judge)
    report = harness.verify(run_id="r3", provider_id="p", model_id="m", results=RESULTS)
    assert report["proof_level"] == "frontier_verification_mismatch"
    assert len(report["mismatches"]) == 1
    mismatch = report["mismatches"][0]
    assert mismatch["dimension"] == "anchor_selection_quality"
    assert mismatch["assessment"] == "over_claim"
    # The weak result is recorded unchanged, not upgraded.
    assert mismatch["weak_outcome"] == "passed"
    assert mismatch["agrees"] is False


def test_confirms_pass_requires_weak_passed(tmp_path) -> None:
    # A frontier "confirms_pass" on a weak 'failed' result does not count as agreement.
    judge = StaticFrontierJudge({"edit_intent_quality:ei_precise": ("confirms_pass", "mismatched")})
    harness = FrontierVerificationHarness(tmp_path, judge=judge)
    report = harness.verify(
        run_id="r4", provider_id="p", model_id="m",
        results=[{"dimension": "edit_intent_quality", "case_id": "ei_precise", "outcome": "failed", "detail": "x"}],
    )
    verdict = report["verdicts"][0]
    assert verdict["assessment"] == "confirms_pass"
    assert verdict["agrees"] is False


def test_invalid_assessment_becomes_cannot_assess(tmp_path) -> None:
    judge = StaticFrontierJudge({"structured_output_fidelity:sof_schema": ("definitely_pass", "bad label")})
    harness = FrontierVerificationHarness(tmp_path, judge=judge)
    report = harness.verify(
        run_id="r5", provider_id="p", model_id="m",
        results=[{"dimension": "structured_output_fidelity", "case_id": "sof_schema", "outcome": "passed", "detail": "x"}],
    )
    assert report["verdicts"][0]["assessment"] == "cannot_assess"


def test_report_is_persisted(tmp_path) -> None:
    harness = FrontierVerificationHarness(tmp_path)
    report = harness.verify(run_id="r6", provider_id="p", model_id="m", results=RESULTS)
    saved = json.loads(open(report["report_ref"], encoding="utf-8").read())
    assert saved["run_id"] == "r6"
