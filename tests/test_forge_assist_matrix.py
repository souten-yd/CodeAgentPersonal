from agent.model_forge.assist_matrix import AssistMatrixEvaluator, AssistMatrixResult
from agent.model_forge.execution_policy import ModelCapabilityProfile
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass, default_routes_for_class
from agent.twin_control_plane.contracts import ModelCapabilityMode
from agent.model_forge.profile_store import ProfileStore


def _profile():
    return ModelCapabilityProfile(model_id="weak", capability_scores={"large_file_editing": 0.4}, known_weaknesses=["large_file_editing"], mode=ModelCapabilityMode.WEAK_LOCAL)


def test_candidates_stay_in_route_matrix_and_low_readiness_caps_slots():
    evaluator = AssistMatrixEvaluator()
    candidates = evaluator.generate_candidates(provider_id="local", source_mode="local_only", change_class=ChangeClass.LARGE, task_category="codegen", profile=_profile(), readiness_level="low")
    assert candidates
    assert {item.route for item in candidates}.issubset(set(default_routes_for_class(ChangeClass.LARGE)))
    assert len({item.route for item in candidates}) >= 2
    assert all("twin_localized" not in item.twin_assist_mode.value for item in candidates)
    assert all(MethodVariant.REVIEW_ONLY in item.fallback_chain for item in candidates)


def test_local_only_excludes_external_provider():
    assert AssistMatrixEvaluator().generate_candidates(provider_id="openrouter", source_mode="local_only", change_class=ChangeClass.MEDIUM, task_category="codegen", profile=_profile(), readiness_level="high") == []


def test_harm_candidate_cannot_win():
    evaluator = AssistMatrixEvaluator()
    candidates = evaluator.generate_candidates(provider_id="local", source_mode="local_only", change_class=ChangeClass.LARGE, task_category="codegen", profile=_profile(), readiness_level="high")
    results = [AssistMatrixResult(candidate_id=candidates[0].candidate_id, case_id="c", status="passed", score=0.8), AssistMatrixResult(candidate_id=candidates[-1].candidate_id, case_id="c", status="passed", score=1.0, harm_detected=True)]
    report = evaluator.build_report(provider_id="local", model_id="weak", task_category="codegen", change_class=ChangeClass.LARGE, candidates=candidates, results=results)
    assert report.best_candidate_id == candidates[0].candidate_id
    assert report.recommended_policy_patch["task_category"] == "codegen"
    assert report.recommended_policy_patch["change_class"] == "large"


def test_matrix_recommendation_is_saved_by_task_and_change_class(tmp_path):
    evaluator = AssistMatrixEvaluator(); candidates = evaluator.generate_candidates(provider_id="local", source_mode="local_only", change_class=ChangeClass.LARGE, task_category="codegen", profile=_profile(), readiness_level="high")
    report = evaluator.build_report(provider_id="local", model_id="weak", task_category="codegen", change_class=ChangeClass.LARGE, candidates=candidates, results=[AssistMatrixResult(candidate_id=candidates[0].candidate_id, case_id="c", status="passed", score=0.8, evidence_refs=["matrix.json"])])
    profile = ProfileStore(tmp_path).record_assist_matrix_report(report)
    assert profile.assist_matrix_recommendations["codegen:large"]["best_route"] in {route.value for route in default_routes_for_class(ChangeClass.LARGE)}
