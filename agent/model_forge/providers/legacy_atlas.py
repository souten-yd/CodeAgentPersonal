"""Legacy Atlas Executor adapter (PFG-7).

Wraps the existing Atlas model execution path (the structured-JSON backend used by
the planner / patch generator, i.e. AtlasLLMJsonAdapter's
``backend_fn(system_prompt, user_prompt) -> str | dict | None``) behind the Forge
provider interface so Forge can observe/shadow it without changing behavior.

Legacy stays primary: this adapter is not wired into any production path here. It only
makes the legacy executor describable and runnable through ProviderRegistry for
shadow comparison. No stage cutover happens in this package.

Inventory of the legacy model-execution callers this wraps:
- agent/atlas_llm_json_adapter.py :: AtlasLLMJsonAdapter (call_openai_compatible /
  _post_chat / _post_chat_stream) — the structured-output execution path that Atlas
  planning, patch generation, verification interpretation, and repair use via
  app.state.atlas_llm_json_fn.
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

# (system_prompt, user_prompt) -> raw model output, mirroring AtlasLLMJsonAdapter.backend_fn.
BackendFn = Callable[[str, str], "str | dict | None"]
# Resolve a Forge request into the (system, user) prompts the legacy backend expects.
PromptResolver = Callable[[ForgeExecutionRequest], "tuple[str, str]"]
# Persist raw output and return a reference (e.g. into a future evidence store).
OutputSink = Callable[[str, str], str]

LEGACY_ATLAS_PROVIDER_ID = "legacy_atlas"


def legacy_atlas_descriptor() -> ProviderDescriptor:
    """Local, enabled-by-default legacy executor (it is the existing primary path);
    it needs no credential and makes no external call."""
    return ProviderDescriptor(
        provider_id=LEGACY_ATLAS_PROVIDER_ID,
        provider_type="legacy_atlas",
        source_class=SourceClass.LOCAL,
        enabled=True,
        supports=ProviderSupport(
            chat_completions=True, streaming=True, model_catalog=False,
            tool_calling="model_dependent", structured_outputs="model_dependent",
        ),
    )


def _approx_tokens(text: str) -> int:
    # Whitespace-word heuristic, consistent with the legacy streaming token counter.
    return len(str(text or "").split())


class LegacyAtlasProvider(ForgeProvider):
    def __init__(
        self,
        *,
        backend_fn: BackendFn | None,
        prompt_resolver: PromptResolver,
        descriptor: ProviderDescriptor | None = None,
        model_id: str = "legacy_atlas_default",
        output_sink: OutputSink | None = None,
    ) -> None:
        super().__init__(descriptor or legacy_atlas_descriptor())
        self._backend_fn = backend_fn
        self._prompt_resolver = prompt_resolver
        self._model_id = model_id
        self._output_sink = output_sink

    def _probe_health(self) -> ProviderHealth:
        # The legacy path is local and always-on, but is unavailable (not error) until a
        # backend is actually wired in.
        if self._backend_fn is None:
            return ProviderHealth(provider_id=self.provider_id, state=HealthState.UNAVAILABLE, detail="legacy_backend_unwired")
        return ProviderHealth(provider_id=self.provider_id, state=HealthState.READY)

    def run_and_capture(self, request: ForgeExecutionRequest) -> "tuple[ForgeExecutionResult, str]":
        """Execute and return both the structured result and the raw output text, so a
        shadow observer can compare candidates without depending on an evidence store."""
        start = time.monotonic()
        if self._backend_fn is None:
            return self._error_result(request, start, "legacy_backend_unwired"), ""
        try:
            system_prompt, user_prompt = self._prompt_resolver(request)
            raw = self._backend_fn(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001 — never crash the shadow path.
            return self._error_result(request, start, f"legacy_execution_error:{type(exc).__name__}"), ""
        latency_ms = int((time.monotonic() - start) * 1000)
        text = raw if isinstance(raw, str) else (json.dumps(raw, ensure_ascii=False) if raw is not None else "")
        contract_valid = bool(text.strip())
        raw_ref = ""
        if self._output_sink is not None and text:
            try:
                raw_ref = self._output_sink(request.request_id, text)
            except Exception:  # noqa: BLE001 — sink failure must not fail execution.
                raw_ref = ""
        result = ForgeExecutionResult(
            request_id=request.request_id,
            provider_id=self.provider_id,
            model_id=self._model_id,
            route_id=request.route_id,
            stage=request.stage,
            raw_output_ref=raw_ref,
            contract_valid=contract_valid,
            latency_ms=latency_ms,
            usage=ForgeUsage(
                input_tokens=_approx_tokens(f"{system_prompt} {user_prompt}"),
                output_tokens=_approx_tokens(text),
            ),
            errors=[] if contract_valid else ["legacy_empty_output"],
        )
        return result, text

    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        result, _text = self.run_and_capture(request)
        return result

    def _error_result(self, request: ForgeExecutionRequest, start: float, error: str) -> ForgeExecutionResult:
        return ForgeExecutionResult(
            request_id=request.request_id,
            provider_id=self.provider_id,
            model_id=self._model_id,
            route_id=request.route_id,
            stage=request.stage,
            contract_valid=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            errors=[error],
        )
