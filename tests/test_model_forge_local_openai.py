import json
import os
import urllib.request

import pytest

from agent.model_forge import (
    ForgeExecutionRequest,
    ForgeRoute,
    ForgeStage,
    HealthState,
    LocalOpenAICompatibleProvider,
    ProviderRegistry,
    ProviderUnavailableError,
    SourceClass,
    local_openai_compatible_descriptor,
)


def _request() -> ForgeExecutionRequest:
    return ForgeExecutionRequest(request_id="req_1", stage=ForgeStage.PATCH_GENERATION, route_id=ForgeRoute.PATCH_DSL)


def _resolver(_request):
    return ("system", "reply OK")


def _chat_body(content: str, *, prompt_tokens=5, completion_tokens=2) -> str:
    return json.dumps({
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


def _provider(http_post, *, base_url="http://localhost:9999", model_id="m-local", enabled=True):
    return LocalOpenAICompatibleProvider(
        base_url=base_url, model_id=model_id, prompt_resolver=_resolver,
        http_post=http_post, enabled=enabled, timeout_seconds=5,
    )


def test_descriptor_is_self_hosted_not_external_and_no_credential() -> None:
    d = local_openai_compatible_descriptor("http://localhost:8080")
    assert d.source_class == SourceClass.SELF_HOSTED
    assert d.source_class != SourceClass.EXTERNAL_CLOUD
    assert d.credential_env == ""
    assert d.supports.streaming is False  # non-streaming first


def test_successful_completion_parses_content_and_usage() -> None:
    seen = {}

    def http_post(url, payload, timeout):
        seen["url"] = url
        seen["payload"] = payload
        return 200, _chat_body("OK", prompt_tokens=7, completion_tokens=3)

    provider = _provider(http_post)
    result = provider.execute_chat_completion(_request())
    assert seen["url"] == "http://localhost:9999/v1/chat/completions"
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["model"] == "m-local"
    assert result.contract_valid is True
    assert result.usage.input_tokens == 7
    assert result.usage.output_tokens == 3
    assert result.errors == []


def test_http_error_is_classified() -> None:
    provider = _provider(lambda u, p, t: (500, "boom"))
    result = provider.execute_chat_completion(_request())
    assert result.contract_valid is False
    assert result.errors == ["http_500"]


def test_timeout_and_connection_errors_are_classified() -> None:
    def timeout_post(u, p, t):
        raise TimeoutError("timed out")

    def conn_post(u, p, t):
        raise ConnectionError("refused")

    assert _provider(timeout_post).execute_chat_completion(_request()).errors == ["timeout"]
    assert _provider(conn_post).execute_chat_completion(_request()).errors == ["connection_error"]


def test_malformed_response_is_classified() -> None:
    provider = _provider(lambda u, p, t: (200, "not json"))
    result = provider.execute_chat_completion(_request())
    assert result.errors == ["malformed_response"]


def test_empty_content_is_invalid_contract() -> None:
    provider = _provider(lambda u, p, t: (200, _chat_body("   ")))
    result = provider.execute_chat_completion(_request())
    assert result.contract_valid is False
    assert result.errors == ["empty_output"]


def test_missing_base_url_is_unavailable_and_fails_closed() -> None:
    provider = _provider(lambda u, p, t: (200, _chat_body("x")), base_url="")
    assert provider.health_check().state == HealthState.UNAVAILABLE
    reg = ProviderRegistry()
    reg.register(provider)
    with pytest.raises(ProviderUnavailableError):
        reg.execute("local_openai_compatible", _request())


def test_disabled_provider_is_disabled() -> None:
    provider = _provider(lambda u, p, t: (200, _chat_body("x")), enabled=False)
    assert provider.health_check().state == HealthState.DISABLED


def _server_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3):  # noqa: S310
            return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _server_reachable("http://localhost:8080/health"),
    reason="no local OpenAI-compatible server on :8080",
)
def test_real_local_server_smoke() -> None:
    """Real local-provider evidence when a llama.cpp/LM Studio server is up on :8080.
    Skipped in CI where no such server runs (acceptance: no network unless local)."""
    provider = LocalOpenAICompatibleProvider(
        base_url="http://localhost:8080", model_id="", prompt_resolver=lambda r: ("", "Reply with exactly: OK"),
        timeout_seconds=120,
    )
    result = provider.execute_chat_completion(_request())
    assert result.contract_valid is True
    assert result.latency_ms >= 0
    assert result.errors == []
