"""Capability rescue wired into ExecutionPolicySelector (execution-time rescue)."""
from __future__ import annotations

from agent.model_forge.capability_rescue import FallbackModelRef
from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.method_policy import PatchConstructionMode
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass

ALL_WEAK = {
    "structured_output_fidelity": 0.1,
    "patch_protocol_fidelity": 0.1,
    "edit_intent_quality": 0.1,
    "anchor_selection_quality": 0.1,
}


def _policy(scores, **kw):
    return ExecutionPolicySelector().select(
        ChangeClass.MEDIUM,
        model_profile=ModelCapabilityProfile(model_id="m", capability_scores=scores),
        **kw,
    )


def test_all_fail_model_is_rescued_to_deterministic_text():
    policy = _policy(ALL_WEAK)
    assert policy.method_variant == MethodVariant.DETERMINISTIC_TEXT_PATCH
    assert policy.patch_construction_mode == PatchConstructionMode.DETERMINISTIC_TEXT
    assert any("capability_rescue=deterministic_text_patch" in r for r in policy.reasons)


def test_all_fail_with_capable_fallback_escalates():
    fb = FallbackModelRef(provider_id="fp", model_id="strong",
                          capability_scores={"structured_output_fidelity": 0.95})
    policy = _policy(ALL_WEAK, rescue_fallback_model=fb)
    assert policy.method_variant == MethodVariant.STRUCTURED_PATCH_JSON
    assert any("capability_rescue=escalate_fallback_model" in r and "strong" in r for r in policy.reasons)


def test_partial_profile_is_not_rescued():
    # Only structured measured-weak; the router (not rescue) handles it.
    policy = _policy({"structured_output_fidelity": 0.3})
    assert policy.method_variant == MethodVariant.EDIT_INTENT_LIST
    assert not any("capability_rescue" in r for r in policy.reasons)


def test_capable_model_is_not_rescued():
    policy = _policy({
        "structured_output_fidelity": 0.9, "patch_protocol_fidelity": 0.9,
        "edit_intent_quality": 0.9, "anchor_selection_quality": 0.9,
    })
    assert not any("capability_rescue" in r for r in policy.reasons)
    assert policy.method_variant != MethodVariant.DETERMINISTIC_TEXT_PATCH


def test_rescue_preserves_safe_apply_authority():
    policy = _policy(ALL_WEAK)
    # Safe Apply / remote approval gates remain regardless of rescue.
    assert "SafeApplyBoundary" in policy.required_gates
    assert "RemotePublishApprovalGate" in policy.required_gates
    # Review-only terminal is always reachable in the fallback chain.
    assert MethodVariant.REVIEW_ONLY in policy.method_fallbacks
