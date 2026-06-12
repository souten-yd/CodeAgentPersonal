import pytest

from agent.model_forge import (
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeProvider,
    ForgeRoute,
    ForgeStage,
    PrivacyMode,
    ProviderDescriptor,
    ProviderRegistry,
    SourceClass,
    SourceMode,
    privacy_allowed_for_provider,
    provider_availability_matrix,
    resolve_provider_policy,
    select_eligible_provider_ids,
    source_class_allowed,
)


class _Stub(ForgeProvider):
    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        return ForgeExecutionResult(request_id=request.request_id, provider_id=self.provider_id, model_id="m", route_id=request.route_id, stage=request.stage)


def _registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(_Stub(ProviderDescriptor(provider_id="local", provider_type="t", source_class=SourceClass.LOCAL, enabled=True)))
    reg.register(_Stub(ProviderDescriptor(
        provider_id="openrouter", provider_type="openrouter", source_class=SourceClass.EXTERNAL_CLOUD, enabled=True,
        privacy_capabilities=[PrivacyMode.NO_EXTERNAL_CODE, PrivacyMode.SYMBOL_SUMMARY_ONLY],
    )))
    return reg


def test_source_class_allowed_rules() -> None:
    assert source_class_allowed(SourceMode.LOCAL_ONLY, SourceClass.LOCAL) is True
    assert source_class_allowed(SourceMode.LOCAL_ONLY, SourceClass.EXTERNAL_CLOUD) is False
    assert source_class_allowed(SourceMode.FRONTIER_ONLY, SourceClass.LOCAL) is False
    assert source_class_allowed(SourceMode.FRONTIER_ONLY, SourceClass.EXTERNAL_CLOUD) is True
    assert source_class_allowed(SourceMode.HYBRID, SourceClass.EXTERNAL_CLOUD) is True


def test_local_only_makes_external_provider_unselectable(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")  # irrelevant; stub has no credential_env
    reg = _registry()
    eligible = select_eligible_provider_ids(reg, source_mode=SourceMode.LOCAL_ONLY, privacy_mode=PrivacyMode.NO_EXTERNAL_CODE)
    assert eligible == ["local"]
    decision = resolve_provider_policy(reg, "openrouter", source_mode=SourceMode.LOCAL_ONLY, privacy_mode=PrivacyMode.NO_EXTERNAL_CODE)
    assert decision.selectable is False
    assert "source_mode_forbids_provider" in decision.reasons


def test_privacy_mode_unsupported_blocks_external_provider() -> None:
    reg = _registry()
    # openrouter only supports no_external_code/symbol_summary_only; full_source_allowed is unsupported.
    decision = resolve_provider_policy(reg, "openrouter", source_mode=SourceMode.HYBRID, privacy_mode=PrivacyMode.FULL_SOURCE_ALLOWED)
    assert decision.privacy_allowed is False
    assert decision.selectable is False
    assert "privacy_mode_unsupported" in decision.reasons
    # A supported privacy mode makes it selectable in an external-allowing source mode.
    ok = resolve_provider_policy(reg, "openrouter", source_mode=SourceMode.HYBRID, privacy_mode=PrivacyMode.SYMBOL_SUMMARY_ONLY)
    assert ok.selectable is True


def test_local_provider_privacy_always_allowed() -> None:
    reg = _registry()
    assert privacy_allowed_for_provider(reg.get("local").descriptor, PrivacyMode.FULL_SOURCE_ALLOWED) is True
    decision = resolve_provider_policy(reg, "local", source_mode=SourceMode.LOCAL_ONLY, privacy_mode=PrivacyMode.FULL_SOURCE_ALLOWED)
    assert decision.selectable is True


def test_disabled_provider_is_unselectable_with_health_reason() -> None:
    reg = ProviderRegistry()
    reg.register(_Stub(ProviderDescriptor(provider_id="off", provider_type="t", source_class=SourceClass.EXTERNAL_CLOUD, enabled=False)))
    decision = resolve_provider_policy(reg, "off", source_mode=SourceMode.HYBRID, privacy_mode=PrivacyMode.NO_EXTERNAL_CODE)
    assert decision.selectable is False
    assert any(r.startswith("health_") for r in decision.reasons)


def test_availability_matrix_is_api_ready_and_records_decision() -> None:
    reg = _registry()
    matrix = provider_availability_matrix(reg, source_mode=SourceMode.LOCAL_ONLY, privacy_mode=PrivacyMode.NO_EXTERNAL_CODE)
    by_id = {d.provider_id: d for d in matrix}
    assert set(by_id) == {"local", "openrouter"}
    assert by_id["local"].selectable is True
    assert by_id["openrouter"].selectable is False
    # Decision is serializable evidence with the recorded source/privacy modes.
    dumped = by_id["openrouter"].model_dump(mode="json")
    assert dumped["source_mode"] == "local_only"
    assert dumped["privacy_mode"] == "no_external_code"
    assert dumped["decided_at"]
