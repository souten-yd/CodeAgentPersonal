from agent.model_forge import (
    OpenRouterConfig,
    SourceClass,
    SourceMode,
    build_openrouter_headers,
    check_openrouter_allowed,
    live_smoke_enabled,
    openrouter_api_key,
    openrouter_credentials_available,
    openrouter_descriptor,
    redact_openrouter_headers,
)


def test_openrouter_is_disabled_by_default_and_external() -> None:
    cfg = OpenRouterConfig()
    assert cfg.enabled is False
    assert cfg.api_key_env == "OPENROUTER_API_KEY"
    d = openrouter_descriptor()
    assert d.enabled is False
    assert d.source_class == SourceClass.EXTERNAL_CLOUD


def test_api_key_is_read_only_from_env_and_never_persisted(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-123")
    cfg = OpenRouterConfig(enabled=True)
    assert openrouter_api_key(cfg) == "sk-secret-123"
    assert openrouter_credentials_available(cfg) is True
    # The secret must never appear in a serialized config (safe to persist/log).
    dumped = cfg.model_dump_json()
    assert "sk-secret-123" not in dumped
    assert "secret" not in dumped.lower() or "api_key_env" in dumped  # only the env NAME is stored


def test_local_only_blocks_openrouter_before_request(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    cfg = OpenRouterConfig(enabled=True)
    gate = check_openrouter_allowed(cfg, SourceMode.LOCAL_ONLY)
    assert gate.allowed is False
    assert gate.reason == "local_only_blocks_external"


def test_disabled_and_missing_key_are_gated(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Disabled (even in a mode that allows external).
    assert check_openrouter_allowed(OpenRouterConfig(enabled=False), SourceMode.HYBRID).reason == "openrouter_disabled"
    # Enabled but no key.
    assert check_openrouter_allowed(OpenRouterConfig(enabled=True), SourceMode.HYBRID).reason == "missing_openrouter_api_key"


def test_allowed_when_enabled_keyed_and_external_mode(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    gate = check_openrouter_allowed(OpenRouterConfig(enabled=True), SourceMode.FRONTIER_PREFERRED)
    assert gate.allowed is True
    assert gate.reason == ""


def test_headers_carry_key_but_redaction_masks_it(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-xyz")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.test")
    headers = build_openrouter_headers(OpenRouterConfig(enabled=True))
    assert headers["Authorization"] == "Bearer sk-secret-xyz"
    assert headers["HTTP-Referer"] == "https://example.test"
    assert headers["X-Title"]
    redacted = redact_openrouter_headers(headers)
    assert redacted["Authorization"] == "[redacted]"
    assert "sk-secret-xyz" not in str(redacted)


def test_live_smoke_requires_optin_and_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    monkeypatch.delenv("FORGE_OPENROUTER_LIVE_SMOKE", raising=False)
    cfg = OpenRouterConfig(enabled=True)
    assert live_smoke_enabled(cfg) is False
    monkeypatch.setenv("FORGE_OPENROUTER_LIVE_SMOKE", "1")
    assert live_smoke_enabled(cfg) is True
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert live_smoke_enabled(cfg) is False
