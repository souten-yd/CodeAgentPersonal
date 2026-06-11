import pytest

from agent.model_forge import (
    ForgeExecutionRequest,
    ForgeRoute,
    ForgeStage,
    HealthState,
    LegacyAtlasProvider,
    ProviderRegistry,
    SourceClass,
    legacy_atlas_descriptor,
)


def _request() -> ForgeExecutionRequest:
    return ForgeExecutionRequest(request_id="req_1", stage=ForgeStage.PATCH_GENERATION, route_id=ForgeRoute.PATCH_DSL)


def _resolver(_request):
    return ("system prompt", "user prompt asking for a patch")


def test_descriptor_is_local_enabled_no_credential() -> None:
    d = legacy_atlas_descriptor()
    assert d.provider_id == "legacy_atlas"
    assert d.source_class == SourceClass.LOCAL
    assert d.enabled is True
    assert d.credential_env == ""


def test_wraps_backend_and_produces_contract_result() -> None:
    calls = []

    def backend(system, user):
        calls.append((system, user))
        return '{"target_files": ["a.html"], "proposed_content": "<html></html>"}'

    provider = LegacyAtlasProvider(backend_fn=backend, prompt_resolver=_resolver, model_id="mistral-local")
    assert provider.health_check().state == HealthState.READY

    result, raw = provider.run_and_capture(_request())
    assert calls == [("system prompt", "user prompt asking for a patch")]
    assert result.provider_id == "legacy_atlas"
    assert result.model_id == "mistral-local"
    assert result.stage == ForgeStage.PATCH_GENERATION
    assert result.route_id == ForgeRoute.PATCH_DSL
    assert result.contract_valid is True
    assert result.usage.output_tokens > 0
    assert "proposed_content" in raw
    assert result.errors == []


def test_unwired_backend_is_unavailable_and_fails_closed_via_registry() -> None:
    provider = LegacyAtlasProvider(backend_fn=None, prompt_resolver=_resolver)
    assert provider.health_check().state == HealthState.UNAVAILABLE
    reg = ProviderRegistry()
    reg.register(provider)
    # Registry refuses to execute an unavailable provider.
    from agent.model_forge import ProviderUnavailableError

    with pytest.raises(ProviderUnavailableError):
        reg.execute("legacy_atlas", _request())


def test_backend_exception_becomes_error_not_crash() -> None:
    def boom(system, user):
        raise RuntimeError("backend down")

    provider = LegacyAtlasProvider(backend_fn=boom, prompt_resolver=_resolver)
    result = provider.execute_chat_completion(_request())
    assert result.contract_valid is False
    assert any("legacy_execution_error" in e for e in result.errors)


def test_empty_output_is_invalid_contract() -> None:
    provider = LegacyAtlasProvider(backend_fn=lambda s, u: "  ", prompt_resolver=_resolver)
    result = provider.execute_chat_completion(_request())
    assert result.contract_valid is False
    assert "legacy_empty_output" in result.errors


def test_output_sink_receives_raw_and_ref_is_recorded() -> None:
    captured = {}

    def sink(request_id, text):
        captured[request_id] = text
        return f"evidence://{request_id}"

    provider = LegacyAtlasProvider(backend_fn=lambda s, u: "ok output", prompt_resolver=_resolver, output_sink=sink)
    result = provider.execute_chat_completion(_request())
    assert captured["req_1"] == "ok output"
    assert result.raw_output_ref == "evidence://req_1"


def test_registry_executes_legacy_provider_when_ready() -> None:
    provider = LegacyAtlasProvider(backend_fn=lambda s, u: "result text", prompt_resolver=_resolver)
    reg = ProviderRegistry()
    reg.register(provider)
    assert reg.ready_providers() == ["legacy_atlas"]
    result = reg.execute("legacy_atlas", _request())
    assert result.contract_valid is True
