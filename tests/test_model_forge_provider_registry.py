import pytest

from agent.model_forge import (
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeProvider,
    ForgeRoute,
    ForgeStage,
    HealthState,
    ProviderDescriptor,
    ProviderDisabledError,
    ProviderError,
    ProviderRegistry,
    ProviderUnavailableError,
    SourceClass,
    redact_for_log,
)


class _StubProvider(ForgeProvider):
    """Records whether execute ever ran, to prove disabled/unavailable providers
    are never executed."""

    def __init__(self, descriptor: ProviderDescriptor) -> None:
        super().__init__(descriptor)
        self.executed = False

    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        self.executed = True
        return ForgeExecutionResult(
            request_id=request.request_id, provider_id=self.provider_id, model_id="m1",
            route_id=request.route_id, stage=request.stage, contract_valid=True,
        )


def _request() -> ForgeExecutionRequest:
    return ForgeExecutionRequest(request_id="req_1", stage=ForgeStage.PATCH_GENERATION, route_id=ForgeRoute.PATCH_DSL)


def _provider(provider_id="p", *, enabled=True, credential_env="", source_class=SourceClass.LOCAL) -> _StubProvider:
    return _StubProvider(ProviderDescriptor(
        provider_id=provider_id, provider_type="stub", source_class=source_class,
        enabled=enabled, credential_env=credential_env,
    ))


def test_enabled_local_provider_is_ready_and_executes() -> None:
    reg = ProviderRegistry()
    provider = _provider("local", enabled=True)
    reg.register(provider)
    assert reg.health("local").state == HealthState.READY
    result = reg.execute("local", _request())
    assert provider.executed is True
    assert result.provider_id == "local"


def test_disabled_provider_is_never_executed() -> None:
    reg = ProviderRegistry()
    provider = _provider("ext", enabled=False, source_class=SourceClass.EXTERNAL_CLOUD)
    reg.register(provider)
    assert reg.health("ext").state == HealthState.DISABLED
    with pytest.raises(ProviderDisabledError):
        reg.execute("ext", _request())
    assert provider.executed is False


def test_missing_credentials_do_not_crash_and_are_unavailable_not_failed(monkeypatch) -> None:
    monkeypatch.delenv("FORGE_TEST_KEY", raising=False)
    reg = ProviderRegistry()
    provider = _provider("ext", enabled=True, credential_env="FORGE_TEST_KEY", source_class=SourceClass.EXTERNAL_CLOUD)
    reg.register(provider)
    health = reg.health("ext")  # must not raise
    assert health.state == HealthState.UNAVAILABLE
    assert health.detail == "missing_credential"
    with pytest.raises(ProviderUnavailableError):
        reg.execute("ext", _request())
    assert provider.executed is False
    # Once the credential is present the provider becomes ready and runs.
    monkeypatch.setenv("FORGE_TEST_KEY", "secret")
    assert reg.health("ext").state == HealthState.READY
    reg.execute("ext", _request())
    assert provider.executed is True


def test_unknown_provider_health_is_error_not_exception() -> None:
    reg = ProviderRegistry()
    assert reg.health("missing").state == HealthState.ERROR
    with pytest.raises(ProviderError):
        reg.execute("missing", _request())


def test_health_check_exception_is_recorded_as_error() -> None:
    class _Boom(_StubProvider):
        def health_check(self):  # type: ignore[override]
            raise RuntimeError("kaboom")

    reg = ProviderRegistry()
    reg.register(_Boom(ProviderDescriptor(provider_id="boom", provider_type="stub", source_class=SourceClass.LOCAL, enabled=True)))
    health = reg.health("boom")  # must not propagate
    assert health.state == HealthState.ERROR
    assert "health_check_exception" in health.detail


def test_redact_for_log_masks_secrets_and_source() -> None:
    payload = {
        "authorization": "Bearer abc",
        "api_key": "sk-123",
        "messages": [{"role": "user", "content": "private source code"}],
        "model_id": "m1",
        "nested": {"token": "t", "ok": "keep"},
    }
    out = redact_for_log(payload)
    assert out["authorization"] == "[redacted]"
    assert out["api_key"] == "[redacted]"
    assert out["messages"] == "[redacted]"
    assert out["model_id"] == "m1"
    assert out["nested"]["token"] == "[redacted]"
    assert out["nested"]["ok"] == "keep"


def test_ready_providers_excludes_disabled_and_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("FORGE_TEST_KEY", raising=False)
    reg = ProviderRegistry()
    reg.register(_provider("ready", enabled=True))
    reg.register(_provider("off", enabled=False))
    reg.register(_provider("nocred", enabled=True, credential_env="FORGE_TEST_KEY"))
    assert reg.ready_providers() == ["ready"]
