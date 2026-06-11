"""Local / self-hosted OpenAI-compatible provider adapter (PFG-8).

Talks to a local OpenAI-compatible server (llama.cpp server, LM Studio, vLLM, …) via
non-streaming POST {base_url}/v1/chat/completions. Local source class — never assumes
external cloud and needs no external credential. The HTTP transport is injectable so
tests run without a live server; the default transport uses urllib and only touches the
network when actually executed.
"""
from __future__ import annotations

import json
import time
from typing import Callable

from agent.model_forge.provider_base import ForgeProvider, HealthState, ProviderHealth
from agent.model_forge.schema import (
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeUsage,
    ProviderDescriptor,
    ProviderSupport,
    SourceClass,
)

# (system, user) prompts for the request.
PromptResolver = Callable[[ForgeExecutionRequest], "tuple[str, str]"]
# (url, json_payload, timeout_seconds) -> (status_code, body_text). Must raise
# TimeoutError on timeout and ConnectionError on an unreachable backend.
HttpPost = Callable[[str, dict, float], "tuple[int, str]"]

LOCAL_OPENAI_PROVIDER_ID = "local_openai_compatible"


def local_openai_compatible_descriptor(base_url: str = "", *, enabled: bool = True) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider_id=LOCAL_OPENAI_PROVIDER_ID,
        provider_type="local_openai_compatible",
        source_class=SourceClass.SELF_HOSTED,
        enabled=enabled,
        credential_env="",
        base_url=base_url,
        supports=ProviderSupport(
            chat_completions=True, streaming=False, model_catalog=True,
            tool_calling="model_dependent", structured_outputs="model_dependent",
        ),
    )


def _default_http_post(url: str, payload: dict, timeout: float) -> "tuple[int, str]":
    import socket
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — local trusted URL
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
            raise TimeoutError(str(reason)) from exc
        raise ConnectionError(str(reason)) from exc


class LocalOpenAICompatibleProvider(ForgeProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        prompt_resolver: PromptResolver,
        descriptor: ProviderDescriptor | None = None,
        timeout_seconds: float = 120.0,
        http_post: HttpPost | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(descriptor or local_openai_compatible_descriptor(base_url, enabled=enabled))
        self._base_url = str(base_url or "").rstrip("/")
        self._model_id = model_id
        self._prompt_resolver = prompt_resolver
        self._timeout = float(timeout_seconds)
        self._http_post = http_post or _default_http_post

    def _probe_health(self) -> ProviderHealth:
        # No network probe by default (keeps CI offline): READY once a base URL is set,
        # UNAVAILABLE (not error) when it is missing.
        if not self._base_url:
            return ProviderHealth(provider_id=self.provider_id, state=HealthState.UNAVAILABLE, detail="missing_base_url")
        return ProviderHealth(provider_id=self.provider_id, state=HealthState.READY)

    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        start = time.monotonic()
        system_prompt, user_prompt = self._prompt_resolver(request)
        payload: dict = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": 0,
        }
        # Only pin a model when one is configured; single-model servers reject an empty id.
        if self._model_id:
            payload["model"] = self._model_id
        endpoint = f"{self._base_url}/v1/chat/completions"
        try:
            status, body = self._http_post(endpoint, payload, self._timeout)
        except TimeoutError:
            return self._error_result(request, start, "timeout")
        except ConnectionError:
            return self._error_result(request, start, "connection_error")
        except Exception as exc:  # noqa: BLE001 — classify, never crash the caller.
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
        response_model = str(data.get("model") or "") if isinstance(data, dict) else ""
        return ForgeExecutionResult(
            request_id=request.request_id,
            provider_id=self.provider_id,
            model_id=self._model_id or response_model or self.provider_id,
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
