from __future__ import annotations

import pytest
from pydantic import ValidationError

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
from agent.model_forge.route_taxonomy import ForgeRoute


EXPECTED_VARIANTS = {
    "structured_patch_json",
    "patch_dsl_json",
    "edit_intent_list",
    "anchored_edit_block",
    "unified_diff",
    "tool_call_patch",
    "deterministic_text_patch",
    "deterministic_ast_patch",
    "review_only",
    "test_plan_only",
    "repair_compass_steps",
    "twin_localized_slot_patch",
    "twin_symbol_window_patch",
    "twin_deterministic_anchor_patch",
    "twin_slot_fill_only",
}


def _request() -> MethodRequest:
    return MethodRequest(
        request_id="req-1",
        route=ForgeRoute.DIRECT_PATCH,
        method_variant=MethodVariant.STRUCTURED_PATCH_JSON,
        model_id="model-1",
        provider_id="provider-1",
        goal="make the requested change",
    )


def _result(status: str = "passed") -> MethodResult:
    return MethodResult(
        request_id="req-1",
        method_variant=MethodVariant.STRUCTURED_PATCH_JSON,
        status=status,
    )


def test_method_variant_values_are_stable():
    assert {variant.value for variant in MethodVariant} == EXPECTED_VARIANTS


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CompiledPrompt, {"prompt_text": "prompt"}),
        (MethodRequest, _request().model_dump()),
        (MethodResult, _result().model_dump()),
        (
            FallbackStep,
            {"method_variant": MethodVariant.EDIT_INTENT_LIST},
        ),
        (
            MethodChain,
            {"chain_id": "chain-1", "primary": MethodVariant.STRUCTURED_PATCH_JSON},
        ),
        (
            MethodPipelineResult,
            {
                "chain_id": "chain-1",
                "final_status": "passed",
                "selected_method": MethodVariant.STRUCTURED_PATCH_JSON,
            },
        ),
    ],
)
def test_method_dtos_construct_and_forbid_extra_fields(model, payload):
    model.model_validate(payload)
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "unexpected": True})


def test_method_registry_dispatches_by_variant():
    class Adapter:
        variant = MethodVariant.STRUCTURED_PATCH_JSON

        def prepare_prompt(self, request):
            return CompiledPrompt(prompt_text=request.goal)

        def parse_output(self, request, raw_output):
            return _result()

        def compile_patch(self, request, result):
            return result

        def verify_contract(self, request, result):
            return result

    adapter = Adapter()
    registry = MethodRegistry()
    registry.register(adapter)

    assert registry.supports(MethodVariant.STRUCTURED_PATCH_JSON)
    assert registry.get(MethodVariant.STRUCTURED_PATCH_JSON) is adapter
    assert not registry.supports(MethodVariant.EDIT_INTENT_LIST)
    with pytest.raises(KeyError):
        registry.get(MethodVariant.EDIT_INTENT_LIST)


def test_unavailable_method_result_is_not_passed():
    result = _result("unavailable")
    assert result.status == "unavailable"
    assert result.status != "passed"
