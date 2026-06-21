"""PR19: Multi-model role assignment + live eval-dimension expansion."""
from __future__ import annotations

from agent.model_forge.multimodel_optimizer import (
    ROLE_DIMENSIONS,
    ModelCandidate,
    MultiModelRoleOptimizer,
)
from agent.model_forge.real_method_runner import _METHOD_BY_DIMENSION
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.schema import ModelProfile
from agent.model_forge.source_policy import SourceMode


def _candidate(model_id, scores, *, provider="local_openai_compatible", latency=1000, cost=0.0, local=True):
    return ModelCandidate(
        provider_id=provider,
        model_id=model_id,
        profile=ModelProfile(model_id=model_id, provider_id=provider, dimension_scores=scores, sample_count=5),
        estimated_latency_ms=latency,
        cost_tier=cost,
        local_only_safe=local,
    )


def _by_role(result):
    return {a.role: a for a in result.assignments}


def test_assigns_best_model_per_role():
    coder = _candidate("coder-model", {
        "structured_output_fidelity": 0.9, "patch_protocol_fidelity": 0.9,
        "edit_intent_quality": 0.85, "large_file_editing": 0.8,
    })
    reviewer = _candidate("review-model", {
        "evidence_discipline": 0.95, "contract_preservation": 0.9, "stale_test_judgment": 0.85,
    })
    result = MultiModelRoleOptimizer().assign([coder, reviewer])
    roles = _by_role(result)
    assert roles["implementer"].model_id == "coder-model"
    assert roles["verifier"].model_id == "review-model"
    assert roles["reviewer"].model_id == "review-model"
    # Review roles never construct a patch.
    assert roles["reviewer"].method_variant == MethodVariant.REVIEW_ONLY
    assert roles["verifier"].method_variant == MethodVariant.REVIEW_ONLY
    assert roles["reviewer"].fallback_methods == []


def test_local_only_excludes_external_provider():
    local = _candidate("local-model", {"structured_output_fidelity": 0.6})
    external = _candidate("ext-model", {"structured_output_fidelity": 0.99}, provider="openrouter", local=False)
    result = MultiModelRoleOptimizer().assign([local, external], source_mode=SourceMode.LOCAL_ONLY)
    assert "openrouter:ext-model" not in result.eligible_models
    for assignment in result.assignments:
        assert assignment.provider_id != "openrouter"
    assert any("excluded_external_in_local_only" in r for r in result.reasons)


def test_privacy_sensitive_excludes_external_even_if_allowed():
    local = _candidate("local-model", {"structured_output_fidelity": 0.6})
    external = _candidate("ext-model", {"structured_output_fidelity": 0.99}, provider="openrouter", local=False)
    result = MultiModelRoleOptimizer().assign(
        [local, external], source_mode=SourceMode.HYBRID, privacy_sensitive=True,
    )
    assert "openrouter:ext-model" not in result.eligible_models


def test_missing_evidence_recorded_not_assumed():
    sparse = _candidate("sparse", {"structured_output_fidelity": 0.8})
    result = MultiModelRoleOptimizer().assign([sparse])
    by_role = {e.role: e for e in result.role_evidence}
    planner_ev = by_role["planner"]
    # planner needs impact_analysis/abstraction_tolerance/scope_boundary_discipline, none measured.
    assert set(planner_ev.missing_evidence) == set(ROLE_DIMENSIONS["planner"])


def test_higher_latency_loses_when_scores_tie():
    fast = _candidate("fast", {"structured_output_fidelity": 0.8, "patch_protocol_fidelity": 0.8,
                               "edit_intent_quality": 0.8, "large_file_editing": 0.8}, latency=200)
    slow = _candidate("slow", {"structured_output_fidelity": 0.8, "patch_protocol_fidelity": 0.8,
                               "edit_intent_quality": 0.8, "large_file_editing": 0.8}, latency=9000)
    result = MultiModelRoleOptimizer().assign([fast, slow], latency_weight=0.001)
    assert _by_role(result)["implementer"].model_id == "fast"


def test_fallback_model_is_assigned():
    a = _candidate("a", {"structured_output_fidelity": 0.7, "impact_analysis": 0.7,
                         "evidence_discipline": 0.7, "repair_discipline": 0.7})
    b = _candidate("b", {"structured_output_fidelity": 0.95})
    result = MultiModelRoleOptimizer().assign([a, b])
    assert result.fallback_model is not None
    assert result.fallback_model.role == "fallback"
    # The most well-rounded model (a) should back up, not the spiky one (b).
    assert result.fallback_model.model_id == "a"


def test_no_eligible_models_is_honest():
    external = _candidate("ext", {"structured_output_fidelity": 0.9}, provider="openrouter", local=False)
    result = MultiModelRoleOptimizer().assign([external], source_mode=SourceMode.LOCAL_ONLY)
    assert result.status == "no_eligible_models"
    assert result.assignments == []
    assert result.fallback_model is None


def test_live_eval_dimension_expansion_added_method_backed_axes():
    # PR19 expanded live coverage to method-backed dimensions; H2 then moved
    # evidence_discipline / repair_discipline to the semantic evaluator.
    assert _METHOD_BY_DIMENSION["large_file_editing"] == MethodVariant.ANCHORED_EDIT_BLOCK
    assert _METHOD_BY_DIMENSION["edit_intent_quality"] == MethodVariant.EDIT_INTENT_LIST
    # Moved to the semantic LiveCapabilityEvaluator (H2) — no longer format-only method cases.
    assert "anchor_selection_quality" not in _METHOD_BY_DIMENSION
    assert "evidence_discipline" not in _METHOD_BY_DIMENSION
    assert "repair_discipline" not in _METHOD_BY_DIMENSION
    # Non-method dimensions remain unmapped in the method runner.
    assert "abstraction_tolerance" not in _METHOD_BY_DIMENSION
    assert "fallback_recovery" not in _METHOD_BY_DIMENSION
