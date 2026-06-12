"""OpenRouter chat client behind the Forge provider interface (PFG-10).

Implements non-streaming chat completions against OpenRouter with a bounded timeout,
request/response normalization, and usage/latency/error capture. The HTTP transport is
injectable so every test uses a mock — no live API call happens unless the explicit
live-smoke flags are set (FORGE_OPENROUTER_LIVE_SMOKE=1 + OPENROUTER_API_KEY). Local
Only source mode and a disabled/credential-less config fail closed before any request.
"""
from __future__ import annotations

import json
import time
from typing import Callable

from agent.model_forge.provider_base import ForgeProvider, HealthState, ProviderHealth
from agent.model_forge.providers.openrouter_config import (
    OpenRouterConfig,
    build_openrouter_headers,
    check_openrouter_allowed,
    openrouter_credentials_available,
    openrouter_descriptor,
)
from agent.model_forge.schema import ForgeExecutionRequest, ForgeExecutionResult, ForgeUsage
from agent.model_forge.source_policy import SourceMode

PromptResolver = Callable[[ForgeExecutionRequest], "tuple[str, str]"]
# (url, json_payload, headers, timeout) -> (status, body). Must raise TimeoutError on
# timeout and ConnectionError on an unreachable host.
HttpPost = Callable[[str, dict, dict, float], "tuple[int, str]"]


def _default_http_post(url: str, payload: dict, headers: dict, timeout: float) -> "tuple[int, str]":
    import socket
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
            raise TimeoutError(str(reason)) from exc
        raise ConnectionError(str(reason)) from exc


class OpenRouterProvider(ForgeProvider):
    def __init__(
        self,
        *,
        config: OpenRouterConfig | None = None,
        model_id: str,
        prompt_resolver: PromptResolver,
        http_post: HttpPost | None = None,
    ) -> None:
        self.config = config or OpenRouterConfig()
        super().__init__(openrouter_descriptor(enabled=self.config.enabled))
        self._model_id = model_id
        self._prompt_resolver = prompt_resolver
        self._http_post = http_post or _default_http_post

    def _probe_health(self) -> ProviderHealth:
        # Base already mapped not-enabled -> DISABLED and missing OPENROUTER_API_KEY ->
        # UNAVAILABLE. Re-affirm credential availability defensively.
        if not openrouter_credentials_available(self.config):
            return ProviderHealth(provider_id=self.provider_id, state=HealthState.UNAVAILABLE, detail="missing_credential")
        return ProviderHealth(provider_id=self.provider_id, state=HealthState.READY)

    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        start = time.monotonic()
        # Per-request source-mode gate: Local Only blocks OpenRouter before any request.
        gate = check_openrouter_allowed(self.config, request.source_mode)
        if not gate.allowed:
            return self._error_result(request, start, gate.reason)
        system_prompt, user_prompt = self._prompt_resolver(request)
        payload: dict = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = build_openrouter_headers(self.config)
        try:
            status, body = self._http_post(endpoint, payload, headers, self.config.request_timeout_seconds)
        except TimeoutError:
            return self._error_result(request, start, "timeout")
        except ConnectionError:
            return self._error_result(request, start, "connection_error")
        except Exception as exc:  # noqa: BLE001
            return self._error_result(request, start, f"transport_error:{type(exc).__name__}")
        latency_ms = int((time.monotonic() - start) * 1000)
        if status != 200:
            return self._error_result(request, start, f"http_{status}", latency_ms)
        try:
            data = json.loads(body)
            text = str(data["choices"][0]["message"]["content"] or "")
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        except Exception:  # noqa: BLE001
            return self._error_result(request, start, "malformed_response", latency_ms)
        contract_valid = bool(text.strip())
        return ForgeExecutionResult(
            request_id=request.request_id,
            provider_id=self.provider_id,
            model_id=self._model_id or str(data.get("model") or "") or self.provider_id,
            route_id=request.route_id,
            stage=request.stage,
            contract_valid=contract_valid,
            latency_ms=latency_ms,
            usage=ForgeUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
            errors=[] if contract_valid else ["empty_output"],
        )

    def _error_result(self, request: ForgeExecutionRequest, start: float, error: str, latency_ms: int | None = None) -> ForgeExecutionResult:
        return ForgeExecutionResult(
            request_id=request.request_id,
            provider_id=self.provider_id,
            model_id=self._model_id or self.provider_id,
            route_id=request.route_id,
            stage=request.stage,
            contract_valid=False,
            latency_ms=latency_ms if latency_ms is not None else int((time.monotonic() - start) * 1000),
            errors=[error],
        )
