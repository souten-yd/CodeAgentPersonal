"""Forge preset runner for real provider evidence (PFH-6).

The runner is intentionally small: it executes one preset/task through the Forge
provider registry, route selector, and mechanical candidate evaluator. Tests may use
it against a live local OpenAI-compatible server; when no server is reachable, the
runner reports unavailable instead of fabricating evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from agent.model_forge.candidate_evaluator import CandidateEvaluation, CandidateEvaluationInput, CandidateEvaluator
from agent.model_forge.provider_base import RuntimeHealth
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.providers.local_openai_compatible import (
    LOCAL_OPENAI_PROVIDER_ID,
    LocalOpenAICompatibleProvider,
)
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeExecutionRequest, ForgeExecutionResult, ForgeModel
from agent.model_forge.source_policy import PrivacyMode, SourceMode
from agent.model_forge.stage_taxonomy import ForgeStage


class PresetRunnerTask(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    preset_id: str
    stage: ForgeStage
    change_class: ChangeClass
    task_category: str = ""
    system_prompt: str
    user_prompt: str
    output_contract: str = "text"
    requested_route: ForgeRoute | None = None
    source_mode: SourceMode = SourceMode.LOCAL_ONLY
    privacy_mode: PrivacyMode = PrivacyMode.NO_EXTERNAL_CODE
    code_artifacts: dict[str, str] = Field(default_factory=dict)
    code_language: str = ""
    focused_tests_passed: bool | None = None
    portal_runtime_passed: bool | None = None
    requirement_coverage_ratio: float | None = None


class PresetRunnerResult(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    runner_path: str = "ProviderRegistry/LocalOpenAICompatibleProvider/RouteSelector/CandidateEvaluator"
    preset_id: str
    provider_id: str
    model_id: str
    stage: ForgeStage
    route_id: ForgeRoute
    route_reasons: list[str] = Field(default_factory=list)
    execution_result: ForgeExecutionResult
    raw_output: str = ""
    evaluation: CandidateEvaluation
    runtime_verdict: str = "unavailable"

    def evidence_payload(self, *, package: str, output_excerpt_chars: int = 400) -> dict:
        return {
            "package": package,
            "schema_version": self.schema_version,
            "runner_path": self.runner_path,
            "preset_id": self.preset_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "stage": self.stage.value,
            "route_id": self.route_id.value,
            "route_reasons": self.route_reasons,
            "latency_ms": self.execution_result.latency_ms,
            "input_tokens": self.execution_result.usage.input_tokens,
            "output_tokens": self.execution_result.usage.output_tokens,
            "contract_valid": self.execution_result.contract_valid,
            "errors": list(self.execution_result.errors),
            "candidate_verdict": self.evaluation.verdict,
            "candidate_score": self.evaluation.score.final_score,
            "runtime_verdict": self.runtime_verdict,
            "output_excerpt": self.raw_output[:output_excerpt_chars],
        }


class LocalForgePresetRunner:
    def __init__(self, *, base_url: str, model_id: str = "", timeout_seconds: float = 180.0) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.model_id = str(model_id or "")
        self.timeout_seconds = float(timeout_seconds)
        self._last_probe_error = ""

    def probe(self) -> bool:
        provider = LocalOpenAICompatibleProvider(
            base_url=self.base_url,
            model_id=self.model_id,
            prompt_resolver=lambda _request: ("", ""),
            timeout_seconds=min(self.timeout_seconds, 10.0),
        )
        health = provider.probe_runtime()
        self._last_probe_error = health.last_probe_error or health.detail
        return health.runtime_health == RuntimeHealth.READY

    @property
    def unavailable_reason(self) -> str:
        return self._last_probe_error or "local_model_server_unavailable"

    def run(self, task: PresetRunnerTask) -> PresetRunnerResult:
        route = RouteSelector(RouteMatrix()).select(
            task.change_class,
            task_category=task.task_category,
            requested_route=task.requested_route,
        )
        registry = ProviderRegistry()
        registry.register(LocalOpenAICompatibleProvider(
            base_url=self.base_url,
            model_id=self.model_id,
            prompt_resolver=lambda _request: (task.system_prompt, task.user_prompt),
            timeout_seconds=self.timeout_seconds,
            runtime_health=RuntimeHealth.READY.value,
        ))
        request = ForgeExecutionRequest(
            request_id=task.preset_id,
            stage=task.stage,
            route_id=route.selected_route,
            task_category=task.task_category,
            source_mode=task.source_mode,
            privacy_mode=task.privacy_mode,
            output_contract=task.output_contract,
        )
        execution_result, raw_output = registry.run_and_capture(LOCAL_OPENAI_PROVIDER_ID, request)
        evaluation = CandidateEvaluator().evaluate(CandidateEvaluationInput(
            candidate_id=f"{task.preset_id}:{execution_result.provider_id}:{execution_result.model_id}",
            execution_result=execution_result,
            output_contract=task.output_contract,
            raw_output=raw_output,
            code_artifacts=task.code_artifacts,
            code_language=task.code_language,
            focused_tests_passed=task.focused_tests_passed,
            portal_runtime_passed=task.portal_runtime_passed,
            requirement_coverage_ratio=task.requirement_coverage_ratio,
        ))
        runtime_verdict = "passed" if (task.focused_tests_passed or task.portal_runtime_passed) else "unavailable"
        if task.focused_tests_passed is False or task.portal_runtime_passed is False:
            runtime_verdict = "failed"
        return PresetRunnerResult(
            preset_id=task.preset_id,
            provider_id=execution_result.provider_id,
            model_id=execution_result.model_id,
            stage=task.stage,
            route_id=route.selected_route,
            route_reasons=list(route.reasons),
            execution_result=execution_result,
            raw_output=raw_output,
            evaluation=evaluation,
            runtime_verdict=runtime_verdict,
        )


def write_evidence(path: str | Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "LocalForgePresetRunner",
    "PresetRunnerResult",
    "PresetRunnerTask",
    "write_evidence",
]
