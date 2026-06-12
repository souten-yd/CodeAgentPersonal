"""OpenRouter configuration and secret policy (PFG-9).

Config holds only non-secret settings and the NAME of the env var that carries the
API key — never the key value, so the config is safe to persist and log. The key is
read from the environment at request time. OpenRouter is disabled by default and is
blocked entirely in Local Only source mode before any request is constructed. No live
HTTP happens here (the client arrives in PFG-10/PFG-11).
"""
from __future__ import annotations

import os

from agent.model_forge.provider_base import redact_for_log
from agent.model_forge.schema import (
    FORGE_SCHEMA_VERSION,
    ForgeModel,
    PrivacyMode,
    ProviderDescriptor,
    ProviderSupport,
    SourceClass,
)
from agent.model_forge.source_policy import SourceMode, allows_external_providers

OPENROUTER_PROVIDER_ID = "openrouter"
OPENROUTER_LIVE_SMOKE_ENV = "FORGE_OPENROUTER_LIVE_SMOKE"


class OpenRouterConfig(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    enabled: bool = False
    api_key_env: str = "OPENROUTER_API_KEY"
    http_referer_env: str = "OPENROUTER_HTTP_REFERER"
    app_title: str = "KasaneCore Atlas Forge"
    base_url: str = "https://openrouter.ai/api/v1"
    request_timeout_seconds: float = 60.0
    catalog_cache_ttl_seconds: int = 3600
    max_retries: int = 2
    allow_streaming: bool = False


class OpenRouterGate(ForgeModel):
    allowed: bool
    reason: str = ""


def openrouter_descriptor(*, enabled: bool = False) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider_id=OPENROUTER_PROVIDER_ID,
        provider_type="openrouter",
        source_class=SourceClass.EXTERNAL_CLOUD,
        enabled=enabled,
        credential_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        supports=ProviderSupport(
            chat_completions=True, streaming=False, model_catalog=True,
            tool_calling="model_dependent", structured_outputs="model_dependent",
        ),
        privacy_capabilities=[
            PrivacyMode.NO_EXTERNAL_CODE,
            PrivacyMode.SYMBOL_SUMMARY_ONLY,
            PrivacyMode.REDACTED_ONLY,
            PrivacyMode.FULL_SOURCE_ALLOWED,
        ],
    )


def openrouter_api_key(config: OpenRouterConfig) -> str:
    """Read the API key from the environment only. Never stored on the config."""
    return os.environ.get(config.api_key_env, "")


def openrouter_credentials_available(config: OpenRouterConfig) -> bool:
    return bool(openrouter_api_key(config))


def check_openrouter_allowed(config: OpenRouterConfig, source_mode: SourceMode | str) -> OpenRouterGate:
    """Gate OpenRouter use BEFORE any request is constructed. Order matters: Local Only
    blocks external providers regardless of config; then disabled; then missing key."""
    if not allows_external_providers(source_mode):
        return OpenRouterGate(allowed=False, reason="local_only_blocks_external")
    if not config.enabled:
        return OpenRouterGate(allowed=False, reason="openrouter_disabled")
    if not openrouter_credentials_available(config):
        return OpenRouterGate(allowed=False, reason="missing_openrouter_api_key")
    return OpenRouterGate(allowed=True)


def live_smoke_enabled(config: OpenRouterConfig) -> bool:
    """Live OpenRouter smoke runs only when explicitly opted in AND a key exists."""
    return (
        os.environ.get(OPENROUTER_LIVE_SMOKE_ENV, "") == "1"
        and openrouter_credentials_available(config)
    )


def build_openrouter_headers(config: OpenRouterConfig) -> dict:
    """Headers for a real request, including Authorization from the env key. NEVER log
    this dict directly — use redact_openrouter_headers for any logging."""
    headers = {"Content-Type": "application/json"}
    key = openrouter_api_key(config)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    referer = os.environ.get(config.http_referer_env, "")
    if referer:
        headers["HTTP-Referer"] = referer
    if config.app_title:
        headers["X-Title"] = config.app_title
    return headers


def redact_openrouter_headers(headers: dict) -> dict:
    return redact_for_log(headers)  # type: ignore[return-value]
