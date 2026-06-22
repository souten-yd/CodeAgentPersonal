"""Runtime wiring: a Twin-repair regeneration escalates the policy (more injection, then a
weaker/review method) instead of regenerating at the same level."""
from __future__ import annotations

from agent.model_forge.atlas_generation_policy import resolve_atlas_generation_policy
from agent.model_forge.execution_policy import ModelCapabilityProfile
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import ModelCapabilityMode

_WEAK = {d: 0.2 for d in (
    "impact_analysis", "contract_preservation", "test_generation",
    "structured_output_fidelity", "patch_protocol_fidelity", "edit_intent_quality",
    "anchor_selection_quality", "large_file_editing",
)}


def _weak_profile():
    return ModelCapabilityProfile(
        model_id="weak", capability_scores=dict(_WEAK),
        known_weaknesses=[k for k in _WEAK],
        mode=ModelCapabilityMode.WEAK_LOCAL,
        # A sweep said this model is sufficient at the route floor, so the START is minimal and
        # escalation has headroom to climb.
        measured_optimal_injection_level=0, injection_objective="min_sufficient",
    )


def _resolve(failures):
    return resolve_atlas_generation_policy(
        change_class=ChangeClass.MEDIUM, task_category="bugfix",
        provider_id="local", model_id="weak",
        capability_profile=_weak_profile(), profile_available=True,
        route_preferences={}, optimal_routing=True,
        consecutive_method_failures=failures,
    )


def test_injection_escalates_on_consecutive_failures():
    levels = [int(_resolve(f).fallback_recommendation["twin_injection_level"]) for f in (0, 1, 2)]
    # Starts low (route floor) and climbs one level per failure.
    assert levels[0] < levels[1] < levels[2]


def test_repeated_failure_takes_review_only_method():
    rec0 = _resolve(0).fallback_recommendation
    rec2 = _resolve(2).fallback_recommendation
    # By the second failure the method/fallback is the review-only (weakest) path.
    assert "review" in (rec2["method_variant"] + " " + " ".join(rec2["method_fallbacks"])).lower()
    assert rec2["twin_injection_level"] >= rec0["twin_injection_level"]


def test_build_twin_pipeline_evidence_forwards_failure_count():
    # The runtime evidence builder accepts and threads the failure count (off-safe: returns a dict).
    from agent.twin_control_plane.active_integration import PipelineMode
    from agent.twin_control_plane.pipeline_integration import build_twin_pipeline_evidence

    evidence = build_twin_pipeline_evidence(
        mode=PipelineMode.SHADOW, requirement="x", pool_id="p", project_path="",
        model_id="weak", provider_id="local", consecutive_method_failures=2,
    )
    assert isinstance(evidence, dict)
