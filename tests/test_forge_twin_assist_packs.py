from __future__ import annotations

from pathlib import Path

import pytest

from agent.model_forge.twin_assist_contracts import TwinAssistAttemptResult
from agent.model_forge.twin_assist_eval_packs import (
    TWIN_ASSIST_DIMENSIONS,
    TWIN_ASSIST_PACKS,
    aggregate_comparisons,
    compare_twin_assist_case,
    load_twin_assist_cases,
    load_twin_assist_pack,
    validate_fixture,
)
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "twin_assist"


def _attempt(mode, score=None, status="passed"):
    return TwinAssistAttemptResult(
        case_id="case-1",
        assist_mode=mode,
        provider_id="local-8080",
        model_id="weak-model",
        status=status,
        score=score,
    )


def test_full_pack_has_required_cases_and_dimensions():
    cases = load_twin_assist_pack("full")
    assert {case.case_id for case in cases} == set(TWIN_ASSIST_PACKS["full"])
    assert len(cases) == 5
    assert len(TWIN_ASSIST_DIMENSIONS) == 10
    assert all(case.dimension in TWIN_ASSIST_DIMENSIONS for case in cases)


def test_packs_return_deep_copies_and_reject_unknown_ids():
    first = load_twin_assist_pack("quick")
    first[0].target_files.append("mutated.py")
    assert "mutated.py" not in load_twin_assist_pack("quick")[0].target_files
    with pytest.raises(KeyError, match="unknown_twin_assist_pack"):
        load_twin_assist_pack("missing")
    with pytest.raises(KeyError, match="unknown_twin_assist_cases"):
        load_twin_assist_cases(["missing"])


def test_every_catalog_case_has_real_target_and_test_fixtures():
    assert {case.case_id: validate_fixture(case, FIXTURE_ROOT) for case in load_twin_assist_pack("full")} == {
        case_id: [] for case_id in TWIN_ASSIST_PACKS["full"]
    }
    large_fixture = FIXTURE_ROOT / "large_existing_file_insert" / "large_module.py"
    assert len(large_fixture.read_text(encoding="utf-8").splitlines()) >= 200


def test_comparison_selects_best_and_records_lift_and_harm():
    baseline = _attempt(TwinAssistMode.NONE, 0.6)
    assisted = [
        _attempt(TwinAssistMode.STRICT_TWIN_BRIEF, 0.5),
        _attempt(TwinAssistMode.TWIN_LOCALIZED_SLOT, 0.9),
    ]
    result = compare_twin_assist_case("case-1", baseline, assisted)
    assert result.best_assist_mode == TwinAssistMode.TWIN_LOCALIZED_SLOT
    assert result.lift == 0.3
    assert result.harm_detected is True
    assert "harm_detected:strict_twin_brief" in result.reasons


def test_unavailable_evidence_is_never_selected_or_scored():
    result = compare_twin_assist_case(
        "case-1",
        _attempt(TwinAssistMode.NONE, status="unavailable"),
        [_attempt(TwinAssistMode.STRICT_TWIN_BRIEF, status="unavailable")],
    )
    assert result.best_score is None
    assert result.lift is None
    assert result.recommendation == ""
    assert result.reasons == ["baseline_score_unavailable", "assisted_score_unavailable"]


def test_negative_best_lift_retains_baseline():
    result = compare_twin_assist_case(
        "case-1",
        _attempt(TwinAssistMode.NONE, 0.8),
        [_attempt(TwinAssistMode.STRICT_TWIN_BRIEF, 0.7)],
    )
    assert result.lift == -0.1
    assert result.recommendation == "retain_baseline"
    assert result.harm_detected is True


def test_aggregate_reports_harm_rate_without_inventing_missing_scores():
    comparisons = [
        compare_twin_assist_case("one", _attempt(TwinAssistMode.NONE, 0.4), [_attempt(TwinAssistMode.STRICT_TWIN_BRIEF, 0.8)]),
        compare_twin_assist_case("two", _attempt(TwinAssistMode.NONE, 0.8), [_attempt(TwinAssistMode.STRICT_TWIN_BRIEF, 0.6)]),
        compare_twin_assist_case("three", None, [_attempt(TwinAssistMode.STRICT_TWIN_BRIEF, status="unavailable")]),
    ]
    assert aggregate_comparisons(comparisons) == {
        "mean_best_score": 0.7,
        "mean_lift": 0.1,
        "harm_rate": 0.3333,
        "scored_case_count": 2.0,
    }
