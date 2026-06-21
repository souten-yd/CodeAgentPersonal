"""Capability rescue policy: rescue a model that fails its construction methods."""
from __future__ import annotations

from agent.model_forge.capability_rescue import (
    CapabilityRescuePlanner,
    FallbackModelRef,
    RescueLevel,
)
from agent.model_forge.execution_policy import ModelCapabilityProfile
from agent.model_forge.method_taxonomy import MethodVariant
from agent.twin_control_plane.contracts import ModelCapabilityMode

ALL_WEAK = {
    "structured_output_fidelity": 0.1,
    "patch_protocol_fidelity": 0.1,
    "edit_intent_quality": 0.1,
    "anchor_selection_quality": 0.1,
}


def _profile(scores, *, mode=ModelCapabilityMode.STANDARD, weaknesses=None):
    return ModelCapabilityProfile(
        model_id="m", provider_id="p", capability_scores=scores,
        known_weaknesses=weaknesses or [], mode=mode,
    )


def _plan(scores, **kw):
    return CapabilityRescuePlanner().plan(_profile(scores, **kw.pop("profile_kw", {})), **kw)


def test_capable_model_needs_no_rescue():
    plan = CapabilityRescuePlanner().plan(_profile({
        "structured_output_fidelity": 0.9, "patch_protocol_fidelity": 0.8,
    }))
    assert plan.rescue_level == RescueLevel.NONE
    assert plan.primary_method == MethodVariant.STRUCTURED_PATCH_JSON


def test_edit_intent_only_uses_deterministic_compile():
    plan = CapabilityRescuePlanner().plan(_profile({
        "structured_output_fidelity": 0.2, "patch_protocol_fidelity": 0.2,
        "edit_intent_quality": 0.8, "anchor_selection_quality": 0.2,
    }))
    assert plan.rescue_level == RescueLevel.DETERMINISTIC_COMPILE
    assert plan.primary_method == MethodVariant.EDIT_INTENT_LIST


def test_all_weak_escalates_to_capable_fallback_model():
    fb = FallbackModelRef(provider_id="fp", model_id="strong",
                          capability_scores={"structured_output_fidelity": 0.9})
    plan = CapabilityRescuePlanner().plan(_profile(ALL_WEAK), fallback_model=fb)
    assert plan.rescue_level == RescueLevel.ESCALATE_FALLBACK_MODEL
    assert plan.escalate_to_model == "strong"
    assert plan.primary_method == MethodVariant.STRUCTURED_PATCH_JSON


def test_all_weak_no_fallback_uses_deterministic_text():
    plan = CapabilityRescuePlanner().plan(_profile(ALL_WEAK), deterministic_feasible=True)
    assert plan.rescue_level == RescueLevel.DETERMINISTIC_TEXT_PATCH
    assert plan.primary_method == MethodVariant.DETERMINISTIC_TEXT_PATCH


def test_all_weak_no_deterministic_degrades_to_review_only():
    plan = CapabilityRescuePlanner().plan(_profile(ALL_WEAK), deterministic_feasible=False)
    assert plan.rescue_level == RescueLevel.REVIEW_ONLY
    assert plan.primary_method == MethodVariant.REVIEW_ONLY
    assert plan.requires_human_review is True


def test_weak_fallback_model_is_not_escalated_to():
    # A fallback model that is also incapable must not be escalated to.
    fb = FallbackModelRef(provider_id="fp", model_id="alsoweak", capability_scores=ALL_WEAK)
    plan = CapabilityRescuePlanner().plan(_profile(ALL_WEAK), fallback_model=fb, deterministic_feasible=True)
    assert plan.rescue_level == RescueLevel.DETERMINISTIC_TEXT_PATCH


def test_audit_only_mode_is_review_only():
    plan = CapabilityRescuePlanner().plan(_profile(
        {"structured_output_fidelity": 0.9}, mode=ModelCapabilityMode.AUDIT_ONLY,
    ))
    assert plan.rescue_level == RescueLevel.REVIEW_ONLY


def test_every_rescue_chain_ends_in_review_only():
    for scores, kw in [
        ({"structured_output_fidelity": 0.9}, {}),
        ({"edit_intent_quality": 0.8}, {}),
        (ALL_WEAK, {"deterministic_feasible": True}),
        (ALL_WEAK, {"deterministic_feasible": False}),
    ]:
        plan = CapabilityRescuePlanner().plan(_profile(scores), **kw)
        variants = [plan.chain.primary, *[s.method_variant for s in plan.chain.fallbacks]]
        assert MethodVariant.REVIEW_ONLY in variants
        # Authority is always hard-failed.
        assert "safe_apply_bypass" in plan.chain.hard_fail_on


def test_unmeasured_dimensions_are_not_competence():
    # Empty scores -> nothing viable -> rescue (not treated as capable).
    plan = CapabilityRescuePlanner().plan(_profile({}), deterministic_feasible=True)
    assert plan.rescue_level == RescueLevel.DETERMINISTIC_TEXT_PATCH
    assert plan.viable_methods == []
