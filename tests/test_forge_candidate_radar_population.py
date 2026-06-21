"""Arena candidate radar is populated from the model's real benchmark profile."""
from __future__ import annotations

from agent.model_forge.candidate_evaluator import CandidateEvaluationInput, CandidateEvaluator
from agent.model_forge.forge_service import ForgeService
from agent.model_forge.schema import ForgeExecutionResult, ModelProfile


def _evaluation():
    return CandidateEvaluator().evaluate(CandidateEvaluationInput(
        candidate_id="c1",
        execution_result=ForgeExecutionResult(
            request_id="c1", provider_id="local", model_id="m1", route_id="patch_dsl",
            stage="patch_generation", contract_valid=True,
        ),
        output_contract="text", raw_output="ok",
    ))


def test_radar_populated_from_profile(tmp_path):
    svc = ForgeService(str(tmp_path))
    svc.profiles.load_profile = lambda p, m: ModelProfile(
        model_id="m1", provider_id="local",
        dimension_scores={"structured_output_fidelity": 0.9, "edit_intent_quality": 0.3}, sample_count=5,
    )
    enriched = svc._attach_candidate_radar({"provider_id": "local", "model_id": "m1"}, _evaluation())
    assert enriched.score.radar_scores["structured_output_fidelity"] == 0.9
    assert enriched.score.radar_scores["edit_intent_quality"] == 0.3
    # baseline overlay stays empty until an assist-on/off pair exists (never fabricated).
    assert enriched.score.baseline_radar_scores == {}


def test_radar_empty_without_profile_not_fabricated(tmp_path):
    svc = ForgeService(str(tmp_path))
    svc.profiles.load_profile = lambda p, m: None
    enriched = svc._attach_candidate_radar({"provider_id": "local", "model_id": "m1"}, _evaluation())
    assert enriched.score.radar_scores == {}


def test_radar_uses_assist_comparison_when_present(tmp_path):
    svc = ForgeService(str(tmp_path))
    # No plain profile needed; the assist comparison drives the overlay.
    svc.evaluation.load_assist_capability = lambda p, m: {
        "assisted_scores": {"structured_output_fidelity": 0.9, "edit_intent_quality": 0.8},
        "baseline_scores": {"structured_output_fidelity": 0.4, "edit_intent_quality": 0.2},
    }
    enriched = svc._attach_candidate_radar({"provider_id": "local", "model_id": "m1"}, _evaluation())
    assert enriched.score.radar_scores["structured_output_fidelity"] == 0.9  # with assist
    assert enriched.score.baseline_radar_scores["structured_output_fidelity"] == 0.4  # without assist


def test_radar_enrichment_never_raises(tmp_path):
    svc = ForgeService(str(tmp_path))
    def _boom(p, m):
        raise RuntimeError("store down")
    svc.profiles.load_profile = _boom
    enriched = svc._attach_candidate_radar({"provider_id": "local", "model_id": "m1"}, _evaluation())
    assert enriched.score.radar_scores == {}
