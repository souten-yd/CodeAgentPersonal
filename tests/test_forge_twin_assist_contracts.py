from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.model_forge.twin_assist_contracts import (
    TwinAssistAttemptResult,
    TwinAssistCase,
    TwinAssistCaseComparison,
    TwinAssistEvaluationReport,
    TwinAssistRunRequest,
)
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode


EXPECTED_MODES = {
    "none",
    "policy_only",
    "constraints_and_refs",
    "impact_and_safe_edit",
    "strict_twin_brief",
    "twin_localized_slot",
    "twin_deterministic_anchor",
}


def _attempt(status: str = "passed") -> TwinAssistAttemptResult:
    return TwinAssistAttemptResult(
        case_id="case-1",
        assist_mode=TwinAssistMode.NONE,
        provider_id="local-8080",
        model_id="weak-model",
        status=status,
    )


def test_twin_assist_mode_values_are_stable():
    assert {mode.value for mode in TwinAssistMode} == EXPECTED_MODES


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            TwinAssistCase,
            {
                "case_id": "case-1",
                "title": "Large file insert",
                "dimension": "large_file_rescue_success",
                "user_goal": "Add a narrow helper without broad rewrites",
            },
        ),
        (TwinAssistRunRequest, {"provider_id": "local-8080", "model_id": "weak-model"}),
        (TwinAssistAttemptResult, _attempt().model_dump()),
        (TwinAssistCaseComparison, {"case_id": "case-1", "baseline": _attempt().model_dump()}),
        (
            TwinAssistEvaluationReport,
            {
                "run_id": "run-1",
                "provider_id": "local-8080",
                "model_id": "weak-model",
                "status": "passed",
            },
        ),
    ],
)
def test_twin_assist_dtos_construct_and_forbid_extra_fields(model, payload):
    model.model_validate(payload)
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "unexpected": True})


def test_contract_defaults_are_not_shared():
    first = TwinAssistRunRequest(provider_id="local-8080", model_id="model-a")
    second = TwinAssistRunRequest(provider_id="local-8080", model_id="model-b")
    first.case_ids.append("case-1")
    assert second.case_ids == []


def test_unavailable_attempt_is_not_passed():
    result = _attempt("unavailable")
    assert result.status == "unavailable"
    assert result.status != "passed"


@pytest.mark.parametrize("invalid_status", ["ok", "skipped", "unknown"])
def test_attempt_status_is_closed(invalid_status):
    with pytest.raises(ValidationError):
        _attempt(invalid_status)


def test_scores_and_injection_level_are_bounded():
    with pytest.raises(ValidationError):
        TwinAssistAttemptResult(
            case_id="case-1",
            assist_mode=TwinAssistMode.NONE,
            provider_id="local-8080",
            model_id="weak-model",
            status="passed",
            score=1.1,
        )
    with pytest.raises(ValidationError):
        TwinAssistEvaluationReport(
            run_id="run-1",
            provider_id="local-8080",
            model_id="weak-model",
            status="passed",
            recommended_twin_injection_level=5,
        )
