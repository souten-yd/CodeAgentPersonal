import pytest
from pydantic import ValidationError

from agent.model_forge import (
    ArenaCandidate,
    BenchmarkPreset,
    CandidateScore,
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeRoute,
    ForgeStage,
    ModelDescriptor,
    ModelProfile,
    PrivacyMode,
    ProviderDescriptor,
    SourceClass,
    SourceMode,
    StageMode,
    all_routes,
    all_stages,
    allows_external_providers,
    changes_production_routing,
    default_privacy_for_stage,
    default_stage_mode,
    is_privacy_raise,
    is_valid_privacy_mode,
    is_valid_route,
    is_valid_source_mode,
    is_valid_stage,
    privacy_rank,
)


def _samples():
    return [
        ProviderDescriptor(provider_id="openrouter", provider_type="openrouter", source_class=SourceClass.EXTERNAL_CLOUD),
        ModelDescriptor(model_id="qwen-coder-32b", provider_id="llama_cpp_local", source_class=SourceClass.LOCAL, context_window=32768),
        ModelProfile(model_id="m1", provider_id="p1", dimension_scores={"patch_generation": 0.9}),
        BenchmarkPreset(preset_id="web_app_standard", category="web_app", tasks=["fastapi_route_add"], recommended_routes=[ForgeRoute.PATCH_DSL]),
        ForgeExecutionRequest(request_id="forge_req_1", stage=ForgeStage.PATCH_GENERATION, route_id=ForgeRoute.PATCH_DSL),
        ForgeExecutionResult(request_id="forge_req_1", provider_id="llama_cpp_local", model_id="m1", route_id=ForgeRoute.PATCH_DSL, stage=ForgeStage.PATCH_GENERATION),
        ArenaCandidate(candidate_id="cand_1", arena_run_id="arena_1", model_id="m1", provider_id="p1", route_id=ForgeRoute.PATCH_DSL),
        CandidateScore(candidate_id="cand_1", scores={"format": 1.0}, final_score=0.86, verdict="candidate_eligible_for_proposal"),
    ]


@pytest.mark.parametrize("model", _samples())
def test_schema_roundtrips_through_dump_and_validate(model) -> None:
    restored = type(model).model_validate(model.model_dump(mode="json"))
    assert restored == model


def test_schema_rejects_unknown_fields_and_bad_enums() -> None:
    with pytest.raises(ValidationError):
        ProviderDescriptor(provider_id="x", provider_type="y", source_class=SourceClass.LOCAL, bogus_field=1)
    with pytest.raises(ValidationError):
        ModelDescriptor(model_id="m", provider_id="p", source_class="not_a_source_class")
    with pytest.raises(ValidationError):
        ForgeExecutionRequest(request_id="r", stage="not_a_stage", route_id=ForgeRoute.PATCH_DSL)
    with pytest.raises(ValidationError):
        ForgeExecutionRequest(request_id="r", stage=ForgeStage.PLANNING, route_id="not_a_route")
    with pytest.raises(ValidationError):
        ProviderDescriptor(provider_id="", provider_type="y", source_class=SourceClass.LOCAL)


def test_taxonomy_helpers_validate_membership() -> None:
    assert is_valid_stage("patch_generation")
    assert not is_valid_stage("nope")
    assert is_valid_route("patch_dsl")
    assert not is_valid_route("nope")
    assert is_valid_source_mode("local_only")
    assert not is_valid_source_mode("nope")
    assert is_valid_privacy_mode("no_external_code")
    assert not is_valid_privacy_mode("nope")
    assert len(all_stages()) == 13
    assert len(all_routes()) == 11


def test_default_rollout_keeps_forge_off_for_production_routing() -> None:
    # The default mode for every stage must not change live production routing.
    for stage in all_stages():
        assert not changes_production_routing(default_stage_mode(stage))
    # Documented shadow defaults.
    assert default_stage_mode(ForgeStage.PATCH_GENERATION) == StageMode.SHADOW_SELECT
    assert default_stage_mode(ForgeStage.PLANNING) == StageMode.SHADOW_SELECT
    assert default_stage_mode(ForgeStage.FINAL_SUMMARY) == StageMode.DISABLED
    # An unlisted stage defaults to disabled.
    assert default_stage_mode(ForgeStage.CONVERGENCE_DECISION) == StageMode.DISABLED


def test_source_and_privacy_policy_defaults_are_safe() -> None:
    # Local Only blocks external providers; every other mode may use them.
    assert allows_external_providers(SourceMode.LOCAL_ONLY) is False
    assert allows_external_providers(SourceMode.HYBRID) is True
    # Code-bearing stages default to no external code; unlisted stages too.
    assert default_privacy_for_stage(ForgeStage.PATCH_GENERATION) == PrivacyMode.NO_EXTERNAL_CODE
    assert default_privacy_for_stage(ForgeStage.PLANNING) == PrivacyMode.SYMBOL_SUMMARY_ONLY
    assert default_privacy_for_stage(ForgeStage.CONVERGENCE_DECISION) == PrivacyMode.NO_EXTERNAL_CODE
    # Privacy ordering: no_external_code is the most restrictive.
    assert privacy_rank(PrivacyMode.NO_EXTERNAL_CODE) < privacy_rank(PrivacyMode.FULL_SOURCE_ALLOWED)
    assert is_privacy_raise(PrivacyMode.NO_EXTERNAL_CODE, PrivacyMode.REDACTED_ONLY) is True
    assert is_privacy_raise(PrivacyMode.FULL_SOURCE_ALLOWED, PrivacyMode.NO_EXTERNAL_CODE) is False


def test_provider_is_disabled_by_default() -> None:
    provider = ProviderDescriptor(provider_id="openrouter", provider_type="openrouter", source_class=SourceClass.EXTERNAL_CLOUD)
    assert provider.enabled is False
