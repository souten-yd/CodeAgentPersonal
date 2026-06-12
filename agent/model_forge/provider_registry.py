"""Forge provider registry (PFG-6).

Registers providers and gates execution on health. External providers are disabled
by default; a disabled or unavailable provider is never executed. Health checks never
crash on missing credentials — they report UNAVAILABLE, kept distinct from ERROR.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.model_forge.provider_base import (
    ForgeProvider,
    HealthState,
    ProviderDisabledError,
    ProviderError,
    ProviderHealth,
    ProviderUnavailableError,
)
from agent.model_forge.schema import ForgeExecutionRequest, ForgeExecutionResult, ProviderDescriptor


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ForgeProvider] = {}

    def register(self, provider: ForgeProvider) -> None:
        self._providers[provider.provider_id] = provider

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def get(self, provider_id: str) -> ForgeProvider | None:
        return self._providers.get(provider_id)

    def descriptors(self) -> list[ProviderDescriptor]:
        return [provider.descriptor for provider in self._providers.values()]

    def health(self, provider_id: str) -> ProviderHealth:
        """Health for one provider. A provider whose health_check raises unexpectedly
        is reported as ERROR (recorded separately from UNAVAILABLE), never propagated."""
        provider = self._providers.get(provider_id)
        if provider is None:
            return ProviderHealth(
                provider_id=provider_id, state=HealthState.ERROR,
                detail="provider_not_registered",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        try:
            return provider.health_check()
        except Exception as exc:  # noqa: BLE001 — health must never crash the caller.
            return ProviderHealth(
                provider_id=provider_id, state=HealthState.ERROR,
                detail=f"health_check_exception:{type(exc).__name__}",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

    def health_all(self) -> list[ProviderHealth]:
        return [self.health(pid) for pid in self._providers]

    def ready_providers(self) -> list[str]:
        return [pid for pid in self._providers if self.health(pid).state == HealthState.READY]

    def execute(self, provider_id: str, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        """Execute through a provider only when its health is READY. Disabled and
        unavailable providers fail closed before any execute_chat_completion call."""
        provider = self._guarded_provider(provider_id)
        return provider.execute_chat_completion(request)

    def run_and_capture(self, provider_id: str, request: ForgeExecutionRequest) -> "tuple[ForgeExecutionResult, str]":
        """Execute and return raw output when the provider supports capture, while
        preserving the same fail-closed health gate as execute()."""
        provider = self._guarded_provider(provider_id)
        if hasattr(provider, "run_and_capture"):
            return provider.run_and_capture(request)  # type: ignore[attr-defined]
        return provider.execute_chat_completion(request), ""

    def _guarded_provider(self, provider_id: str) -> ForgeProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderError("provider_not_registered", provider_id)
        health = self.health(provider_id)
        if health.state == HealthState.DISABLED:
            raise ProviderDisabledError("provider_disabled", health.detail)
        if health.state == HealthState.UNAVAILABLE:
            raise ProviderUnavailableError("provider_unavailable", health.detail)
        if health.state != HealthState.READY:
            raise ProviderError("provider_not_ready", health.detail)
        return provider
