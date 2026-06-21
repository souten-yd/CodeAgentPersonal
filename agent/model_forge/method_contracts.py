"""Pure contracts for Forge method selection and fallback execution."""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeModel


class CompiledPrompt(ForgeModel):
    prompt_text: str
    system_text: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class MethodRequest(ForgeModel):
    request_id: str = Field(min_length=1)
    route: ForgeRoute
    method_variant: MethodVariant
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    task_category: str = ""
    change_class: str = ""
    goal: str = ""
    context_package_ref: str = ""
    twin_brief_ref: str = ""
    allowed_refs: list[str] = Field(default_factory=list)
    forbidden_refs: list[str] = Field(default_factory=list)
    output_contract: str = ""
    verification_contract: str = ""
    abstraction_level: str = "concrete_steps"
    decomposition_policy: str = "narrow_slice"
    risk_level: str = "medium"
    metadata: dict[str, object] = Field(default_factory=dict)


class MethodResult(ForgeModel):
    request_id: str = Field(min_length=1)
    method_variant: MethodVariant
    status: Literal["passed", "failed", "unavailable", "blocked"]
    raw_output_ref: str = ""
    parsed_output_ref: str = ""
    patch_ref: str = ""
    edit_intent_ref: str = ""
    proposal_ref: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    unavailable_reasons: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    token_usage: dict[str, int] = Field(default_factory=dict)
    contract_valid: bool = False
    safe_apply_ready: bool = False
    requires_human_review: bool = False


class MethodAdapter(Protocol):
    variant: MethodVariant

    def prepare_prompt(self, request: MethodRequest) -> CompiledPrompt: ...

    def parse_output(self, request: MethodRequest, raw_output: str) -> MethodResult: ...

    def compile_patch(self, request: MethodRequest, result: MethodResult) -> MethodResult: ...

    def verify_contract(self, request: MethodRequest, result: MethodResult) -> MethodResult: ...


class MethodRegistry:
    def __init__(self) -> None:
        self._adapters: dict[MethodVariant, MethodAdapter] = {}

    def register(self, adapter: MethodAdapter) -> None:
        self._adapters[adapter.variant] = adapter

    def get(self, variant: MethodVariant) -> MethodAdapter:
        return self._adapters[variant]

    def supports(self, variant: MethodVariant) -> bool:
        return variant in self._adapters


class FallbackStep(ForgeModel):
    method_variant: MethodVariant
    reason: str = ""
    max_attempts: int = Field(default=1, ge=1)
    trigger_on: list[str] = Field(default_factory=list)
    modifies_request: dict[str, object] = Field(default_factory=dict)


class MethodChain(ForgeModel):
    chain_id: str = Field(min_length=1)
    primary: MethodVariant
    fallbacks: list[FallbackStep] = Field(default_factory=list)
    stop_on: list[str] = Field(default_factory=lambda: ["passed"])
    hard_fail_on: list[str] = Field(default_factory=list)


class MethodPipelineResult(ForgeModel):
    chain_id: str = Field(min_length=1)
    final_status: Literal["passed", "failed", "unavailable", "blocked"]
    selected_method: MethodVariant
    attempts: list[MethodResult] = Field(default_factory=list)
    final_patch_ref: str = ""
    final_proposal_ref: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    fallback_reasons: list[str] = Field(default_factory=list)
