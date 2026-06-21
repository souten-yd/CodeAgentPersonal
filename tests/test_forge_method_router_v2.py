"""PR18: MethodRouter v2 — broadened fallback triggers + capability-aware refinements."""
from __future__ import annotations

from agent.model_forge.execution_policy import ModelCapabilityProfile
from agent.model_forge.method_policy import (
    ContextPackageMode,
    InstructionAbstractionLevel,
    PatchConstructionMode,
    RepairMode,
    TaskDecompositionPolicy,
    VerificationMode,
)
from agent.model_forge.method_router import RECOVERABLE_TRIGGERS, MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import ModelCapabilityMode


def _select(profile, *, route=ForgeRoute.PATCH_DSL, change_class=ChangeClass.MEDIUM, fails=0):
    return MethodRouter().select(route=route, change_class=change_class, profile=profile, consecutive_failures=fails)


def test_fallback_triggers_cover_real_failure_vocabulary():
    # The PR16 gap: a weak model fails with content_missing / file_changes_missing, which
    # the original narrow triggers ignored. Every fallback must now trigger on them.
    profile = ModelCapabilityProfile(model_id="weak", capability_scores={"structured_output_fidelity": 0.3})
    decision = _select(profile)
    assert decision.chain.primary == MethodVariant.EDIT_INTENT_LIST
    for step in decision.chain.fallbacks:
        assert "content_missing" in step.trigger_on
        assert "file_changes_missing" in step.trigger_on
    # A review-only terminal guarantees the chain can always recover.
    assert decision.chain.fallbacks[-1].method_variant == MethodVariant.REVIEW_ONLY
    assert "content_missing" in RECOVERABLE_TRIGGERS


def test_abstraction_weakness_uses_fill_in_template():
    profile = ModelCapabilityProfile(model_id="abs", capability_scores={"abstraction_tolerance": 0.45})
    decision = _select(profile)
    assert decision.instruction_abstraction_level == InstructionAbstractionLevel.FILL_IN_TEMPLATE
    assert "abstraction_weakness_uses_template" in decision.reasons


def test_severe_abstraction_weakness_uses_yes_no_gate():
    profile = ModelCapabilityProfile(model_id="abs2", capability_scores={"abstraction_tolerance": 0.2})
    decision = _select(profile)
    assert decision.instruction_abstraction_level == InstructionAbstractionLevel.YES_NO_GATE


def test_context_overload_weakness_uses_minimal_refs():
    profile = ModelCapabilityProfile(model_id="ctx", capability_scores={"context_overload_sensitivity": 0.3})
    decision = _select(profile)
    assert decision.context_package_mode == ContextPackageMode.MINIMAL


def test_test_generation_strength_uses_test_first():
    profile = ModelCapabilityProfile(model_id="tg", capability_scores={"test_generation": 0.85})
    decision = _select(profile)
    assert decision.task_decomposition_policy == TaskDecompositionPolicy.TEST_FIRST_SLICE
    assert decision.verification_mode == VerificationMode.FOCUSED_TESTS


def test_repair_strength_uses_repair_loop():
    profile = ModelCapabilityProfile(model_id="rp", capability_scores={"repair_discipline": 0.9})
    decision = _select(profile)
    assert decision.repair_mode == RepairMode.REPAIR_COMPASS


def test_evidence_weakness_separates_verifier():
    profile = ModelCapabilityProfile(model_id="ev", capability_scores={"evidence_discipline": 0.2})
    decision = _select(profile)
    assert decision.verifier_separation is True
    assert decision.verification_mode == VerificationMode.FULL_GATE


def test_structured_weak_edit_strong_uses_deterministic_compile():
    profile = ModelCapabilityProfile(
        model_id="det",
        capability_scores={"structured_output_fidelity": 0.3, "edit_intent_quality": 0.85},
    )
    decision = _select(profile)
    assert decision.chain.primary == MethodVariant.EDIT_INTENT_LIST
    assert decision.deterministic_compile is True
    assert decision.patch_construction_mode == PatchConstructionMode.DETERMINISTIC_TEXT


def test_frontier_assisted_lowers_injection():
    profile = ModelCapabilityProfile(
        model_id="frontier",
        mode=ModelCapabilityMode.FRONTIER_ASSISTED,
        capability_scores={"impact_analysis": 0.9},
    )
    decision = _select(profile)
    assert decision.lower_injection is True
    assert decision.instruction_abstraction_level == InstructionAbstractionLevel.GUIDED_GOAL
    assert decision.task_decomposition_policy == TaskDecompositionPolicy.LIGHT


def test_unmeasured_dimensions_do_not_trigger_refinements():
    # A legacy profile with only one measured dimension must not pick up strong/weak rules
    # for unmeasured dimensions (default scores must not count as strong or weak).
    profile = ModelCapabilityProfile(model_id="legacy", capability_scores={"impact_analysis": 0.8})
    decision = _select(profile)
    assert decision.repair_mode == RepairMode.FALLBACK_METHOD
    assert decision.verifier_separation is False
    assert decision.deterministic_compile is False
    assert decision.task_decomposition_policy == TaskDecompositionPolicy.NARROW_SLICE


def test_review_only_is_not_refined():
    profile = ModelCapabilityProfile(
        model_id="rev",
        capability_scores={"repair_discipline": 0.9, "evidence_discipline": 0.2},
    )
    decision = _select(profile, fails=2)
    assert decision.chain.primary == MethodVariant.REVIEW_ONLY
    assert decision.patch_construction_mode == PatchConstructionMode.NONE
    assert decision.chain.fallbacks == []
    assert decision.verifier_separation is False
