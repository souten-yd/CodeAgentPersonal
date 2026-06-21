"""Twin Assist case packs and deterministic baseline/assisted scoring."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from agent.model_forge.twin_assist_contracts import (
    TwinAssistAttemptResult,
    TwinAssistCase,
    TwinAssistCaseComparison,
)
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode

TWIN_ASSIST_DIMENSIONS = [
    "twin_assist_lift",
    "twin_instruction_compliance",
    "safe_edit_briefing_utilization",
    "twin_localization_fit",
    "slot_fill_quality",
    "deterministic_anchor_compliance",
    "large_file_rescue_success",
    "cross_file_consistency_with_twin",
    "contract_preservation_with_twin",
    "test_targeting_with_twin",
]

DEFAULT_ASSIST_MODES = [
    TwinAssistMode.POLICY_ONLY,
    TwinAssistMode.CONSTRAINTS_AND_REFS,
    TwinAssistMode.IMPACT_AND_SAFE_EDIT,
    TwinAssistMode.STRICT_TWIN_BRIEF,
    TwinAssistMode.TWIN_LOCALIZED_SLOT,
    TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR,
]

_CASES = [
    TwinAssistCase(
        case_id="large_existing_file_insert",
        title="Large existing file insert",
        dimension="large_file_rescue_success",
        change_class="large",
        target_files=["large_module.py"],
        project_fixture_id="large_existing_file_insert",
        user_goal="Add normalize_label without rewriting unrelated functions.",
        expected_behavior="The helper is added at the unique utility boundary.",
        assist_modes=DEFAULT_ASSIST_MODES,
        expected_symbols=["normalize_label"],
        expected_tests=["test_large_module.py"],
    ),
    TwinAssistCase(
        case_id="cross_file_api_consistency",
        title="Cross-file API consistency",
        dimension="cross_file_consistency_with_twin",
        target_files=["service.py", "test_service.py"],
        project_fixture_id="cross_file_api_consistency",
        user_goal="Add an existing-contract-aware display_name helper and its test.",
        expected_behavior="Implementation and test use the same real symbol.",
        assist_modes=DEFAULT_ASSIST_MODES,
        required_refs=["service.py:User"],
        forbidden_refs=["service.py:Account"],
        expected_symbols=["display_name"],
        expected_tests=["test_service.py"],
    ),
    TwinAssistCase(
        case_id="public_contract_preservation",
        title="Public contract preservation",
        dimension="contract_preservation_with_twin",
        target_files=["contract.py"],
        project_fixture_id="public_contract_preservation",
        user_goal="Handle surrounding whitespace without changing parse_token signature.",
        expected_behavior="The public signature and export remain unchanged.",
        assist_modes=DEFAULT_ASSIST_MODES,
        required_refs=["contract.py:parse_token"],
        expected_symbols=["parse_token"],
        expected_tests=["test_contract.py"],
    ),
    TwinAssistCase(
        case_id="edit_intent_rescue",
        title="Edit intent rescue",
        dimension="slot_fill_quality",
        target_files=["formatter.py"],
        project_fixture_id="edit_intent_rescue",
        user_goal="Add compact output inside the preselected render slot.",
        expected_behavior="Only the slot body is generated; Atlas owns the anchor.",
        assist_modes=[TwinAssistMode.TWIN_LOCALIZED_SLOT, TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR],
        required_refs=["formatter.py:render"],
        expected_symbols=["render"],
        expected_tests=["test_formatter.py"],
    ),
    TwinAssistCase(
        case_id="dependency_aware_test_selection",
        title="Dependency-aware test selection",
        dimension="test_targeting_with_twin",
        target_files=["pricing.py"],
        project_fixture_id="dependency_aware_test_selection",
        user_goal="Clamp negative discounts and select the dependent pricing test.",
        expected_behavior="The proposal targets the dependent test from Twin evidence.",
        assist_modes=DEFAULT_ASSIST_MODES,
        required_refs=["pricing.py:apply_discount"],
        expected_symbols=["apply_discount"],
        expected_tests=["test_pricing.py"],
    ),
]

TWIN_ASSIST_PACKS = {
    "quick": ["public_contract_preservation", "edit_intent_rescue"],
    "large_file": ["large_existing_file_insert", "edit_intent_rescue"],
    "cross_file": ["cross_file_api_consistency", "dependency_aware_test_selection"],
    "contract": ["public_contract_preservation"],
    "full": [case.case_id for case in _CASES],
}


def load_twin_assist_cases(case_ids: Iterable[str] | None = None) -> list[TwinAssistCase]:
    requested = list(case_ids or [])
    by_id = {case.case_id: case for case in _CASES}
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise KeyError(f"unknown_twin_assist_cases:{','.join(unknown)}")
    selected = requested or TWIN_ASSIST_PACKS["full"]
    return [by_id[case_id].model_copy(deep=True) for case_id in selected]


def load_twin_assist_pack(pack_id: str) -> list[TwinAssistCase]:
    if pack_id not in TWIN_ASSIST_PACKS:
        raise KeyError(f"unknown_twin_assist_pack:{pack_id}")
    return load_twin_assist_cases(TWIN_ASSIST_PACKS[pack_id])


def validate_fixture(case: TwinAssistCase, fixture_root: str | Path) -> list[str]:
    root = Path(fixture_root) / case.project_fixture_id
    missing = [path for path in case.target_files if not (root / path).is_file()]
    missing.extend(test for test in case.expected_tests if not (root / test).is_file())
    return sorted(set(missing))


def compare_twin_assist_case(
    case_id: str,
    baseline: TwinAssistAttemptResult | None,
    assisted: list[TwinAssistAttemptResult],
    *,
    harm_delta: float = 0.05,
) -> TwinAssistCaseComparison:
    eligible = [
        attempt for attempt in assisted
        if attempt.status in {"passed", "failed"} and attempt.score is not None
    ]
    best = max(eligible, key=lambda item: (float(item.score), item.assist_mode.value), default=None)
    baseline_score = (
        float(baseline.score)
        if baseline is not None and baseline.status in {"passed", "failed"} and baseline.score is not None
        else None
    )
    lift = round(float(best.score) - baseline_score, 4) if best is not None and baseline_score is not None else None
    harmful = [
        item for item in eligible
        if baseline_score is not None and float(item.score) < baseline_score - harm_delta
    ]
    reasons: list[str] = []
    if baseline_score is None:
        reasons.append("baseline_score_unavailable")
    if best is None:
        reasons.append("assisted_score_unavailable")
    if harmful:
        reasons.append("harm_detected:" + ",".join(item.assist_mode.value for item in harmful))
    recommendation = ""
    if best is not None and (lift is None or lift >= 0):
        recommendation = f"prefer:{best.assist_mode.value}"
    elif best is not None:
        recommendation = "retain_baseline"
    return TwinAssistCaseComparison(
        case_id=case_id,
        baseline=baseline,
        assisted=assisted,
        best_assist_mode=best.assist_mode if best is not None else None,
        best_score=best.score if best is not None else None,
        lift=lift,
        harm_detected=bool(harmful),
        recommendation=recommendation,
        reasons=reasons,
    )


def aggregate_comparisons(comparisons: Iterable[TwinAssistCaseComparison]) -> dict[str, float]:
    items = list(comparisons)
    lifts = [item.lift for item in items if item.lift is not None]
    scored = [item.best_score for item in items if item.best_score is not None]
    return {
        "mean_best_score": round(sum(scored) / len(scored), 4) if scored else 0.0,
        "mean_lift": round(sum(lifts) / len(lifts), 4) if lifts else 0.0,
        "harm_rate": round(sum(item.harm_detected for item in items) / len(items), 4) if items else 0.0,
        "scored_case_count": float(len(scored)),
    }
