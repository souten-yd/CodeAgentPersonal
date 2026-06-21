from pathlib import Path

from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.twin_assist_contracts import TwinAssistAttemptResult, TwinAssistCaseComparison, TwinAssistEvaluationReport
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode
from agent.twin_control_plane.contracts import ModelCapabilityMode


def _report():
    attempt = TwinAssistAttemptResult(case_id="large", assist_mode=TwinAssistMode.TWIN_LOCALIZED_SLOT, provider_id="local", model_id="weak", status="passed", score=0.9)
    return TwinAssistEvaluationReport(run_id="run", provider_id="local", model_id="weak", status="passed", comparisons=[TwinAssistCaseComparison(case_id="large", assisted=[attempt], best_assist_mode=TwinAssistMode.TWIN_LOCALIZED_SLOT, best_score=0.9, lift=0.4)], aggregate_scores={"mean_best_score": 0.9, "mean_lift": 0.4, "harm_rate": 0.0}, recommended_twin_injection_level=4, recommended_assist_modes=[TwinAssistMode.TWIN_LOCALIZED_SLOT], evidence_refs=["run/report.json"])


def test_profile_store_reconstructs_twin_assist_recommendation(tmp_path: Path):
    profile = ProfileStore(tmp_path).record_twin_assist_report(_report())
    assert profile.recommended_twin_assist_mode == "twin_localized_slot"
    assert profile.recommended_twin_injection_level == 4
    assert profile.twin_assist_lift == {"large": 0.4}
    assert profile.evidence_refs == ["run/report.json"]


def test_router_uses_slot_only_when_measured_weak_and_recommended():
    profile = ModelCapabilityProfile(model_id="weak", capability_scores={"large_file_editing": 0.4}, known_weaknesses=["large_file_editing"], mode=ModelCapabilityMode.WEAK_LOCAL, recommended_twin_assist_mode="twin_localized_slot", recommended_twin_injection_level=4)
    decision = MethodRouter().select(route=ForgeRoute.SLICED_IMPACT, change_class=ChangeClass.LARGE, profile=profile)
    assert decision.chain.primary == MethodVariant.TWIN_LOCALIZED_SLOT_PATCH
    assert [step.method_variant for step in decision.chain.fallbacks] == [MethodVariant.REVIEW_ONLY]


def test_execution_policy_caps_recommendation_to_route_and_keeps_gates():
    profile = ModelCapabilityProfile(model_id="weak", capability_scores={"large_file_editing": 0.4, "edit_intent_quality": 0.0}, known_weaknesses=["large_file_editing"], mode=ModelCapabilityMode.WEAK_LOCAL, recommended_twin_assist_mode="twin_localized_slot", recommended_twin_injection_level=4, twin_assist_lift={"large": 0.4})
    policy = ExecutionPolicySelector().select(ChangeClass.MICRO, requested_route=ForgeRoute.MICRO_PATCH, model_profile=profile)
    assert int(policy.twin_injection_level) == 2
    assert policy.twin_assist_mode == "twin_localized_slot"
    assert policy.twin_slot_required is True
    assert policy.twin_assist_expected_lift == 0.4
    assert MethodVariant.EDIT_INTENT_LIST in policy.avoid_method_variants
    assert "SafeApplyBoundary" in policy.required_gates
