from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import Field

from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass, default_routes_for_class
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeModel
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode


class AssistMatrixCandidate(ForgeModel):
    candidate_id: str
    route: ForgeRoute
    method_variant: MethodVariant
    twin_assist_mode: TwinAssistMode
    twin_injection_level: int = Field(ge=0, le=4)
    fallback_chain: list[MethodVariant] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AssistMatrixResult(ForgeModel):
    candidate_id: str
    case_id: str
    status: str
    score: float | None = Field(default=None, ge=0, le=1)
    lift_vs_baseline: float | None = Field(default=None, ge=-1, le=1)
    harm_detected: bool = False
    latency_ms: int = Field(default=0, ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class AssistMatrixReport(ForgeModel):
    report_id: str
    provider_id: str
    model_id: str
    task_category: str
    change_class: str
    candidates: list[AssistMatrixCandidate]
    results: list[AssistMatrixResult]
    best_candidate_id: str = ""
    recommended_policy_patch: dict = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = ""


class AssistMatrixEvaluator:
    def generate_candidates(self, *, provider_id: str, source_mode: str, change_class: ChangeClass, task_category: str, profile: ModelCapabilityProfile, readiness_level: str) -> list[AssistMatrixCandidate]:
        if provider_id in {"openrouter", "openrouter_api"} and source_mode == "local_only":
            return []
        selector = ExecutionPolicySelector()
        # Ask only RouteMatrix-derived defaults; no unsafe requested route is invented.
        modes = [TwinAssistMode.CONSTRAINTS_AND_REFS, TwinAssistMode.STRICT_TWIN_BRIEF]
        if readiness_level in {"high", "trusted"}:
            modes += [TwinAssistMode.TWIN_LOCALIZED_SLOT, TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR]
        candidates = []
        seen: set[tuple] = set()
        for requested_route in default_routes_for_class(change_class):
            base = selector.select(change_class, task_category=task_category, requested_route=requested_route, model_profile=profile)
            for mode in modes:
                method = base.method_variant or MethodVariant.REVIEW_ONLY
                if mode == TwinAssistMode.TWIN_LOCALIZED_SLOT:
                    method = MethodVariant.TWIN_LOCALIZED_SLOT_PATCH
                elif mode == TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR:
                    method = MethodVariant.TWIN_DETERMINISTIC_ANCHOR_PATCH
                fallbacks = list(base.method_fallbacks)
                if change_class in {ChangeClass.LARGE, ChangeClass.CRITICAL} and MethodVariant.REVIEW_ONLY not in fallbacks:
                    fallbacks.append(MethodVariant.REVIEW_ONLY)
                key = (base.route, method, mode)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(AssistMatrixCandidate(candidate_id="matrix_" + uuid4().hex[:10], route=base.route, method_variant=method, twin_assist_mode=mode, twin_injection_level=int(base.twin_injection_level), fallback_chain=fallbacks, metadata={"readiness_level": readiness_level}))
        return candidates

    def build_report(self, *, provider_id: str, model_id: str, task_category: str, change_class: ChangeClass, candidates: list[AssistMatrixCandidate], results: list[AssistMatrixResult]) -> AssistMatrixReport:
        eligible = [result for result in results if result.status == "passed" and result.score is not None and not result.harm_detected and not result.blocked_reasons]
        def rank(result):
            return float(result.score) + max(0.0, float(result.lift_vs_baseline or 0)) - min(0.2, result.latency_ms / 1_000_000)
        best = max(eligible, key=rank, default=None)
        candidate = next((item for item in candidates if best and item.candidate_id == best.candidate_id), None)
        patch = {} if candidate is None else {"task_category": task_category, "change_class": change_class.value, "best_route": candidate.route.value, "best_method_variant": candidate.method_variant.value, "best_twin_assist_mode": candidate.twin_assist_mode.value, "best_injection_level": candidate.twin_injection_level, "fallback_chain": [item.value for item in candidate.fallback_chain]}
        return AssistMatrixReport(report_id="assist_matrix_" + uuid4().hex[:12], provider_id=provider_id, model_id=model_id, task_category=task_category, change_class=change_class.value, candidates=candidates, results=results, best_candidate_id=candidate.candidate_id if candidate else "", recommended_policy_patch=patch, evidence_refs=[ref for result in results for ref in result.evidence_refs], created_at=datetime.now(timezone.utc).isoformat())
