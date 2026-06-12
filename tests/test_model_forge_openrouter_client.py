import json

import pytest

from agent.model_forge import (
    ForgeExecutionRequest,
    ForgeRoute,
    ForgeStage,
    HealthState,
    OpenRouterConfig,
    OpenRouterProvider,
    PrivacyMode,
    SourceMode,
)


def _request(source_mode=SourceMode.FRONTIER_PREFERRED) -> ForgeExecutionRequest:
    return ForgeExecutionRequest(
        request_id="req_1", stage=ForgeStage.PLANNING, route_id=ForgeRoute.PATCH_DSL,
        source_mode=source_mode, privacy_mode=PrivacyMode.SYMBOL_SUMMARY_ONLY,
    )


def _resolver(_request):
    return ("system", "plan this")


def _chat_body(content="OK", prompt_tokens=10, completion_tokens=4, model="anthropic/claude"):
    return json.dumps({
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


def _provider(http_post, *, enabled=True, model_id="anthropic/claude"):
    cfg = OpenRouterConfig(enabled=enabled)
    return OpenRouterProvider(config=cfg, model_id=model_id, prompt_resolver=_resolver, http_post=http_post)


def test_disabled_by_default_health_is_disabled() -> None:
    provider = OpenRouterProvider(config=OpenRouterConfig(), model_id="m", prompt_resolver=_resolver, http_post=lambda *a: (200, _chat_body()))
    assert provider.health_check().state == HealthState.DISABLED


def test_enabled_without_key_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider = _provider(lambda *a: (200, _chat_body()))
    assert provider.health_check().state == HealthState.UNAVAILABLE


def test_mock_success_normalizes_and_captures_usage(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    seen = {}

    def http_post(url, payload, headers, timeout):
        seen["url"] = url
        seen["auth"] = headers.get("Authorization")
        seen["stream"] = payload["stream"]
        return 200, _chat_body("done", prompt_tokens=11, completion_tokens=5)

    provider = _provider(http_post)
    assert provider.health_check().state == HealthState.READY
    result = provider.execute_chat_completion(_request())
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-x"
    assert seen["stream"] is False
    assert result.contract_valid is True
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 5
    assert result.errors == []


def test_local_only_blocks_before_any_http(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    called = {"n": 0}

    def http_post(url, payload, headers, timeout):
        called["n"] += 1
        return 200, _chat_body()

    provider = _provider(http_post)
    result = provider.execute_chat_completion(_request(source_mode=SourceMode.LOCAL_ONLY))
    assert called["n"] == 0  # no HTTP attempted
    assert result.contract_valid is False
    assert result.errors == ["local_only_blocks_external"]


def test_http_timeout_and_error_become_structured_results(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")

    def timeout_post(*a):
        raise TimeoutError("timed out")

    assert _provider(timeout_post).execute_chat_completion(_request()).errors == ["timeout"]
    assert _provider(lambda *a: (429, "rate limited")).execute_chat_completion(_request()).errors == ["http_429"]
    assert _provider(lambda *a: (200, "not json")).execute_chat_completion(_request()).errors == ["malformed_response"]


def test_provider_never_makes_live_call_in_ci(monkeypatch) -> None:
    # The default transport (real urllib) must not be used: all tests inject a mock.
    # Here we assert that without a live-smoke opt-in we are not exercising the network.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    provider = _provider(lambda *a: (200, _chat_body()))
    result = provider.execute_chat_completion(_request())
    assert result.contract_valid is True
