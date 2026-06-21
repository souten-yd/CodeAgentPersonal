from __future__ import annotations

import json

from agent.model_forge.method_contracts import (
    CompiledPrompt,
    FallbackStep,
    MethodChain,
    MethodRegistry,
    MethodRequest,
    MethodResult,
)
from agent.model_forge.method_pipeline import MethodPipeline, MethodUnavailableError
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.remaining_adapters import build_method_registry
from agent.model_forge.route_taxonomy import ForgeRoute


def _request(variant: MethodVariant = MethodVariant.STRUCTURED_PATCH_JSON) -> MethodRequest:
    return MethodRequest(
        request_id="request",
        route=ForgeRoute.PATCH_DSL,
        method_variant=variant,
        model_id="model",
        provider_id="local",
        goal="replace old with new",
    )


def test_schema_invalid_falls_back_to_edit_intent():
    outputs = {
        MethodVariant.STRUCTURED_PATCH_JSON: "not json",
        MethodVariant.EDIT_INTENT_LIST: json.dumps({
            "intents": [{"path": "app.py", "old_text": "old", "new_text": "new"}]
        }),
    }
    chain = MethodChain(
        chain_id="schema-fallback",
        primary=MethodVariant.STRUCTURED_PATCH_JSON,
        fallbacks=[FallbackStep(
            method_variant=MethodVariant.EDIT_INTENT_LIST,
            reason="structured schema recovery",
            trigger_on=["schema_invalid"],
        )],
    )
    result = MethodPipeline(build_method_registry(), lambda request, _prompt: outputs[request.method_variant]).run(
        _request(), chain
    )
    assert result.final_status == "passed"
    assert result.selected_method == MethodVariant.EDIT_INTENT_LIST
    assert [attempt.status for attempt in result.attempts] == ["failed", "passed"]
    assert result.fallback_reasons == ["structured schema recovery"]
    assert result.final_patch_ref


def test_anchor_not_found_falls_back_to_unified_diff():
    diff = """--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-old
+new
"""
    outputs = {
        MethodVariant.ANCHORED_EDIT_BLOCK: "missing markers",
        MethodVariant.UNIFIED_DIFF: diff,
    }
    chain = MethodChain(
        chain_id="anchor-fallback",
        primary=MethodVariant.ANCHORED_EDIT_BLOCK,
        fallbacks=[FallbackStep(
            method_variant=MethodVariant.UNIFIED_DIFF,
            trigger_on=["anchor_not_found"],
        )],
    )
    result = MethodPipeline(build_method_registry(), lambda request, _prompt: outputs[request.method_variant]).run(
        _request(MethodVariant.ANCHORED_EDIT_BLOCK), chain
    )
    assert result.final_status == "passed"
    assert result.selected_method == MethodVariant.UNIFIED_DIFF
    assert result.fallback_reasons == ["anchor_not_found->unified_diff"]


def test_unavailable_is_recorded_and_can_trigger_fallback():
    def invoke(request, _prompt):
        if request.method_variant == MethodVariant.STRUCTURED_PATCH_JSON:
            raise MethodUnavailableError("provider_unavailable")
        return "Review required: provider was unavailable."

    chain = MethodChain(
        chain_id="unavailable-fallback",
        primary=MethodVariant.STRUCTURED_PATCH_JSON,
        fallbacks=[FallbackStep(
            method_variant=MethodVariant.REVIEW_ONLY,
            trigger_on=["provider_unavailable"],
        )],
    )
    result = MethodPipeline(build_method_registry(), invoke).run(_request(), chain)
    assert result.final_status == "passed"
    assert result.attempts[0].status == "unavailable"
    assert result.attempts[0].status != "passed"
    assert result.selected_method == MethodVariant.REVIEW_ONLY


def test_max_attempts_are_recorded_before_fallback():
    calls = 0

    def invoke(request, _prompt):
        nonlocal calls
        calls += 1
        return "not json" if request.method_variant == MethodVariant.STRUCTURED_PATCH_JSON else "review"

    chain = MethodChain(
        chain_id="retry",
        primary=MethodVariant.STRUCTURED_PATCH_JSON,
        fallbacks=[FallbackStep(
            method_variant=MethodVariant.REVIEW_ONLY,
            max_attempts=2,
            trigger_on=["schema_invalid"],
        )],
        stop_on=[],
    )
    result = MethodPipeline(build_method_registry(), invoke).run(_request(), chain)
    assert calls == 3
    assert len(result.attempts) == 3


def test_safe_apply_bypass_hard_fails_without_running_fallback():
    class UnsafeAdapter:
        variant = MethodVariant.TOOL_CALL_PATCH

        def prepare_prompt(self, request):
            return CompiledPrompt(prompt_text="unsafe")

        def parse_output(self, request, raw_output):
            return MethodResult(
                request_id=request.request_id,
                method_variant=self.variant,
                status="passed",
                patch_ref="memory://patch",
                contract_valid=True,
                safe_apply_ready=True,
            )

        def compile_patch(self, request, result):
            return result

        def verify_contract(self, request, result):
            return result

    registry = MethodRegistry()
    registry.register(UnsafeAdapter())
    chain = MethodChain(
        chain_id="hard-fail",
        primary=MethodVariant.TOOL_CALL_PATCH,
        fallbacks=[FallbackStep(method_variant=MethodVariant.REVIEW_ONLY)],
    )
    result = MethodPipeline(registry, lambda _request, _prompt: "unsafe").run(
        _request(MethodVariant.TOOL_CALL_PATCH), chain
    )
    assert result.final_status == "blocked"
    assert len(result.attempts) == 1
    assert result.attempts[0].safe_apply_ready is False
    assert result.blocked_reasons == ["safe_apply_bypass"]


def test_unregistered_adapter_is_unavailable_not_passed():
    result = MethodPipeline(MethodRegistry(), lambda _request, _prompt: "unused").run(
        _request(MethodVariant.TEST_PLAN_ONLY),
        MethodChain(chain_id="missing", primary=MethodVariant.TEST_PLAN_ONLY),
    )
    assert result.final_status == "unavailable"
    assert result.attempts[0].unavailable_reasons == ["adapter_unavailable"]


def test_fallback_modification_cannot_override_route_or_provider():
    chain = MethodChain(
        chain_id="unsafe-modification",
        primary=MethodVariant.STRUCTURED_PATCH_JSON,
        fallbacks=[FallbackStep(
            method_variant=MethodVariant.REVIEW_ONLY,
            trigger_on=["schema_invalid"],
            modifies_request={"route": ForgeRoute.CRITICAL_GATE, "provider_id": "external"},
        )],
    )
    result = MethodPipeline(build_method_registry(), lambda _request, _prompt: "not json").run(
        _request(), chain
    )
    assert result.final_status == "blocked"
    assert result.blocked_reasons == ["invalid_fallback_modification"]
    assert len(result.attempts) == 2
