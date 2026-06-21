"""H3: Full-axis frontier verification across all live dimensions."""
from __future__ import annotations

from agent.model_forge.full_axis_verification import (
    FullAxisFrontierVerifier,
    all_live_dimensions,
)
from agent.model_forge.frontier_verification import StaticFrontierJudge


def test_all_live_dimensions_cover_method_and_semantic():
    dims = set(all_live_dimensions())
    # method-backed
    assert {"structured_output_fidelity", "patch_protocol_fidelity",
            "edit_intent_quality", "large_file_editing"} <= dims
    # semantic / non-method
    assert {"scope_boundary_discipline", "context_overload_sensitivity",
            "abstraction_tolerance", "fallback_recovery",
            "anchor_selection_quality", "evidence_discipline", "repair_discipline"} <= dims
    assert len(dims) == 11


def test_anchor_now_confirmed_not_over_claimed(tmp_path):
    # After H2 the anchor check is semantic, so the frontier confirms the pass.
    results = [
        {"dimension": "anchor_selection_quality", "case_id": "asq_unique", "outcome": "passed",
         "detail": "unique_anchor_selected"},
        {"dimension": "anchor_selection_quality", "case_id": "asq_ambiguous", "outcome": "passed",
         "detail": "unique_anchor_selected"},
    ]
    judge = StaticFrontierJudge({
        "anchor_selection_quality:asq_unique": ("confirms_pass", "anchor verified unique vs file content"),
        "anchor_selection_quality:asq_ambiguous": ("confirms_pass", "ambiguous token would have failed; check is semantic"),
    })
    report = FullAxisFrontierVerifier(tmp_path, judge=judge).verify(
        run_id="r", provider_id="p", model_id="m", results=results,
    )
    assert report["proof_level"] == "frontier_verification_passed"
    assert report["mismatches"] == []


def test_report_lists_uncovered_dimensions(tmp_path):
    results = [
        {"dimension": "structured_output_fidelity", "case_id": "sof_schema", "outcome": "passed", "detail": "ok"},
    ]
    judge = StaticFrontierJudge({"structured_output_fidelity:sof_schema": ("confirms_pass", "strict json")})
    report = FullAxisFrontierVerifier(tmp_path, judge=judge).verify(
        run_id="r2", provider_id="p", model_id="m", results=results,
    )
    assert report["covered_dimensions"] == ["structured_output_fidelity"]
    assert "anchor_selection_quality" in report["uncovered_live_dimensions"]
    assert len(report["all_live_dimensions"]) == 11


def test_genuine_failures_are_confirmed_not_upgraded(tmp_path):
    results = [
        {"dimension": "edit_intent_quality", "case_id": "ei_precise", "outcome": "failed", "detail": "content_missing"},
    ]
    judge = StaticFrontierJudge({
        "edit_intent_quality:ei_precise": ("confirms_fail", "empty anchors are a real failure"),
    })
    report = FullAxisFrontierVerifier(tmp_path, judge=judge).verify(
        run_id="r3", provider_id="p", model_id="m", results=results,
    )
    verdict = report["verdicts"][0]
    assert verdict["assessment"] == "confirms_fail"
    assert verdict["agrees"] is True
    assert verdict["weak_outcome"] == "failed"  # not upgraded
