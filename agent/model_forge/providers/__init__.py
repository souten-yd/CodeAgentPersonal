"""Forge provider implementations.

Provider modules must not import UI modules or FastAPI routers. Each provider wraps a
single execution backend behind the ForgeProvider interface.
"""
from __future__ import annotations

from agent.model_forge.providers.legacy_atlas import (
    LegacyAtlasProvider,
    legacy_atlas_descriptor,
)
from agent.model_forge.providers.local_openai_compatible import (
    LOCAL_OPENAI_PROVIDER_ID,
    LocalOpenAICompatibleProvider,
    local_openai_compatible_descriptor,
)
from agent.model_forge.providers.openrouter_config import (
    OPENROUTER_PROVIDER_ID,
    OpenRouterConfig,
    OpenRouterGate,
    build_openrouter_headers,
    check_openrouter_allowed,
    live_smoke_enabled,
    openrouter_api_key,
    openrouter_credentials_available,
    openrouter_descriptor,
    redact_openrouter_headers,
)

__all__ = [
    "LegacyAtlasProvider",
    "legacy_atlas_descriptor",
    "LocalOpenAICompatibleProvider",
    "local_openai_compatible_descriptor",
    "LOCAL_OPENAI_PROVIDER_ID",
    "OPENROUTER_PROVIDER_ID",
    "OpenRouterConfig",
    "OpenRouterGate",
    "openrouter_descriptor",
    "openrouter_api_key",
    "openrouter_credentials_available",
    "check_openrouter_allowed",
    "live_smoke_enabled",
    "build_openrouter_headers",
    "redact_openrouter_headers",
]
