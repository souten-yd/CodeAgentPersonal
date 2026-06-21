"""Fallback-aware execution pipeline for registered Forge Method adapters."""
from __future__ import annotations

from collections.abc import Callable

from agent.model_forge.method_contracts import (
    CompiledPrompt,
    FallbackStep,
    MethodChain,
    MethodPipelineResult,
    MethodRegistry,
    MethodRequest,
    MethodResult,
)
from agent.model_forge.method_taxonomy import MethodVariant


MethodInvoker = Callable[[MethodRequest, CompiledPrompt], str]

_AUTHORITY_BYPASS_REASONS = {
    "proposal_bypass",
    "safe_apply_bypass",
    "verification_bypass",
}
_ALLOWED_FALLBACK_MODIFICATIONS = {
    "abstraction_level",
    "context_package_ref",
    "decomposition_policy",
    "metadata",
    "output_contract",
    "twin_brief_ref",
    "verification_contract",
}


class MethodUnavailableError(RuntimeError):
    """The selected provider/method cannot run; this is not a passed result."""


class MethodPipeline:
    def __init__(self, registry: MethodRegistry, invoke: MethodInvoker) -> None:
        self._registry = registry
        self._invoke = invoke

    def run(self, request: MethodRequest, chain: MethodChain) -> MethodPipelineResult:
        attempts: list[MethodResult] = []
        fallback_reasons: list[str] = []
        steps = [FallbackStep(method_variant=chain.primary), *chain.fallbacks]
        previous_reasons: list[str] = []
        hard_fail_reasons = set(chain.hard_fail_on) | _AUTHORITY_BYPASS_REASONS

        for index, step in enumerate(steps):
            if index and not self._should_run_fallback(step, previous_reasons):
                continue
            if index:
                fallback_reasons.append(step.reason or self._fallback_reason(previous_reasons, step.method_variant))

            for _attempt_number in range(step.max_attempts):
                try:
                    attempt_request = self._request_for_step(request, step)
                except ValueError:
                    result = MethodResult(
                        request_id=request.request_id,
                        method_variant=step.method_variant,
                        status="blocked",
                        blocked_reasons=["invalid_fallback_modification"],
                    )
                    attempts.append(result)
                    return self._finalize(chain, attempts, fallback_reasons, result)
                result = self._run_attempt(attempt_request)
                result = self._enforce_authority_boundary(result)
                attempts.append(result)
                previous_reasons = self._result_reasons(result)

                matched_hard_fail = sorted(hard_fail_reasons.intersection(previous_reasons))
                if matched_hard_fail:
                    result = result.model_copy(update={
                        "status": "blocked",
                        "contract_valid": False,
                        "safe_apply_ready": False,
                        "blocked_reasons": list(dict.fromkeys([*result.blocked_reasons, *matched_hard_fail])),
                    })
                    attempts[-1] = result
                    return self._finalize(chain, attempts, fallback_reasons, result)

                if result.status in chain.stop_on:
                    return self._finalize(chain, attempts, fallback_reasons, result)

            previous_reasons = self._result_reasons(attempts[-1])

        final = attempts[-1] if attempts else MethodResult(
            request_id=request.request_id,
            method_variant=chain.primary,
            status="failed",
            errors=["no_method_attempted"],
        )
        return self._finalize(chain, attempts, fallback_reasons, final)

    def _run_attempt(self, request: MethodRequest) -> MethodResult:
        if not self._registry.supports(request.method_variant):
            return MethodResult(
                request_id=request.request_id,
                method_variant=request.method_variant,
                status="unavailable",
                unavailable_reasons=["adapter_unavailable"],
            )
        adapter = self._registry.get(request.method_variant)
        prompt = adapter.prepare_prompt(request)
        try:
            raw_output = self._invoke(request, prompt)
        except MethodUnavailableError as exc:
            reason = str(exc).strip() or "provider_unavailable"
            return MethodResult(
                request_id=request.request_id,
                method_variant=request.method_variant,
                status="unavailable",
                unavailable_reasons=[reason],
            )
        except Exception as exc:  # noqa: BLE001 - classify provider failures without crashing the pipeline.
            return MethodResult(
                request_id=request.request_id,
                method_variant=request.method_variant,
                status="failed",
                errors=[f"invocation_error:{type(exc).__name__}"],
            )
        parsed = adapter.parse_output(request, raw_output)
        compiled = adapter.compile_patch(request, parsed)
        return adapter.verify_contract(request, compiled)

    @staticmethod
    def _request_for_step(request: MethodRequest, step: FallbackStep) -> MethodRequest:
        unsupported = set(step.modifies_request).difference(_ALLOWED_FALLBACK_MODIFICATIONS)
        if unsupported:
            raise ValueError("unsupported fallback request modification")
        updates = dict(step.modifies_request)
        updates["method_variant"] = step.method_variant
        return MethodRequest.model_validate({**request.model_dump(mode="python"), **updates})

    @staticmethod
    def _should_run_fallback(step: FallbackStep, previous_reasons: list[str]) -> bool:
        return not step.trigger_on or bool(set(step.trigger_on).intersection(previous_reasons))

    @staticmethod
    def _result_reasons(result: MethodResult) -> list[str]:
        return list(dict.fromkeys([
            *result.errors,
            *result.blocked_reasons,
            *result.unavailable_reasons,
            *([] if result.status == "passed" else [result.status]),
        ]))

    @staticmethod
    def _fallback_reason(previous_reasons: list[str], variant: MethodVariant) -> str:
        reason = previous_reasons[0] if previous_reasons else "previous_method_not_passed"
        return f"{reason}->{variant.value}"

    @staticmethod
    def _enforce_authority_boundary(result: MethodResult) -> MethodResult:
        if result.safe_apply_ready and not result.proposal_ref:
            return result.model_copy(update={
                "status": "blocked",
                "contract_valid": False,
                "safe_apply_ready": False,
                "blocked_reasons": list(dict.fromkeys([*result.blocked_reasons, "safe_apply_bypass"])),
            })
        return result

    @staticmethod
    def _finalize(
        chain: MethodChain,
        attempts: list[MethodResult],
        fallback_reasons: list[str],
        final: MethodResult,
    ) -> MethodPipelineResult:
        evidence_refs = list(dict.fromkeys(
            ref for attempt in attempts for ref in attempt.evidence_refs
        ))
        blocked_reasons = list(dict.fromkeys(
            reason for attempt in attempts for reason in attempt.blocked_reasons
        ))
        return MethodPipelineResult(
            chain_id=chain.chain_id,
            final_status=final.status,
            selected_method=final.method_variant,
            attempts=attempts,
            final_patch_ref=final.patch_ref,
            final_proposal_ref=final.proposal_ref,
            evidence_refs=evidence_refs,
            blocked_reasons=blocked_reasons,
            fallback_reasons=fallback_reasons,
        )
