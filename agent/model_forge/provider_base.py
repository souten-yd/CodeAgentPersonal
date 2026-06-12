"""Forge provider base interface and health model (PFG-6).

Defines the provider abstraction every Forge provider implements, plus the health
taxonomy and a redacted-logging helper. Providers must fail closed: disabled or
credential-less providers report a non-ready health state and must never execute.
No real network calls live here — concrete providers arrive in PFG-7+.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import StrEnum

from agent.model_forge.schema import (
    FORGE_SCHEMA_VERSION,
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeModel,
    ModelDescriptor,
    ProviderDescriptor,
)


class HealthState(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ConfiguredState(StrEnum):
    DISABLED = "disabled"
    MISSING_CONFIG = "missing_config"
    CONFIGURED = "configured"


class RuntimeHealth(StrEnum):
    NOT_PROBED = "not_probed"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


# States that must never run a request. UNAVAILABLE (e.g. missing credential, offline)
# is deliberately distinct from ERROR (an actual failure) so callers can record them
# separately.
NON_EXECUTABLE_STATES: frozenset[HealthState] = frozenset(
    {HealthState.DISABLED, HealthState.UNAVAILABLE, HealthState.ERROR}
)


class ProviderHealth(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    provider_id: str
    state: HealthState
    detail: str = ""
    checked_at: str = ""
    configured_state: ConfiguredState = ConfiguredState.CONFIGURED
    runtime_health: RuntimeHealth = RuntimeHealth.NOT_PROBED
    last_probe_at: str = ""
    last_probe_error: str = ""


class ProviderError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class ProviderDisabledError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


# Keys whose values must never reach a log: credentials and raw source/prompt content.
_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "authorization", "api_key", "apikey", "token", "secret", "credential",
        "password", "messages", "prompt", "system_prompt", "user_prompt",
        "content", "source", "source_code", "raw_output", "parsed_output",
    }
)


def redact_for_log(payload: object) -> object:
    """Recursively mask credential- and source-bearing fields so request/response
    payloads can be logged without leaking secrets or user source code."""
    if isinstance(payload, dict):
        redacted: dict = {}
        for key, value in payload.items():
            if str(key).lower() in _REDACT_KEYS:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_for_log(value)
        return redacted
    if isinstance(payload, (list, tuple)):
        return [redact_for_log(item) for item in payload]
    return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ForgeProvider(ABC):
    """Base class for all Forge providers.

    Concrete providers implement execute_chat_completion and may override the
    optional hooks. The base enforces the fail-closed contract: not-enabled or
    missing-credential providers report a non-ready health state and guard_executable
    raises before any execution can happen."""

    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self.descriptor = descriptor

    @property
    def provider_id(self) -> str:
        return self.descriptor.provider_id

    @property
    def enabled(self) -> bool:
        return bool(self.descriptor.enabled)

    def credential_available(self) -> bool:
        env_name = self.descriptor.credential_env
        if not env_name:
            return True  # local providers need no credential
        return bool(os.environ.get(env_name))

    def health_check(self) -> ProviderHealth:
        """Default health: disabled if not enabled, unavailable if a required
        credential is missing, otherwise delegate to a (overridable) live probe."""
        if not self.enabled:
            return ProviderHealth(
                provider_id=self.provider_id, state=HealthState.DISABLED,
                detail="provider_disabled", checked_at=_now_iso(),
                configured_state=ConfiguredState.DISABLED,
                runtime_health=RuntimeHealth.NOT_PROBED,
            )
        if self.descriptor.credential_env and not self.credential_available():
            return ProviderHealth(
                provider_id=self.provider_id, state=HealthState.UNAVAILABLE,
                detail="missing_credential", checked_at=_now_iso(),
                configured_state=ConfiguredState.MISSING_CONFIG,
                runtime_health=RuntimeHealth.UNAVAILABLE,
                last_probe_error="missing_credential",
            )
        return self._probe_health()

    def _probe_health(self) -> ProviderHealth:
        """Overridable live readiness probe. Default assumes ready once enabled and
        credentialed; real providers may perform a network probe and return
        UNAVAILABLE/ERROR. Must not raise on a normal unreachable backend."""
        checked_at = _now_iso()
        return ProviderHealth(
            provider_id=self.provider_id, state=HealthState.READY, checked_at=checked_at,
            configured_state=ConfiguredState.CONFIGURED,
            runtime_health=RuntimeHealth.READY,
            last_probe_at=checked_at,
        )

    def probe_runtime(self) -> ProviderHealth:
        return self.health_check()

    def guard_executable(self) -> None:
        health = self.health_check()
        if health.state == HealthState.DISABLED:
            raise ProviderDisabledError("provider_disabled", health.detail)
        if health.state == HealthState.UNAVAILABLE:
            raise ProviderUnavailableError("provider_unavailable", health.detail)
        if health.state != HealthState.READY:
            raise ProviderError("provider_not_ready", health.detail)

    def supports_contract(self, output_contract: str) -> bool:
        return True

    def list_models(self) -> list[ModelDescriptor]:
        return []

    def estimate_cost(self, request: ForgeExecutionRequest) -> float | None:
        return None

    def redact_request_for_log(self, request: ForgeExecutionRequest) -> dict:
        return redact_for_log(request.model_dump(mode="json"))  # type: ignore[return-value]

    @abstractmethod
    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        """Run a chat completion. Implementations must assume guard_executable has
        already passed (the registry enforces it) and must fail closed otherwise."""
        raise NotImplementedError
