"""PR22: Validate Atlas planning / code development / completion against the
benchmark-derived optimal route and Twin injection level.

Forge model benchmarks determine an optimal route + Twin injection for a change class
(via ExecutionPolicySelector). This validator checks that the Atlas execution phases
respect RouteMatrix authority, carry the required evidence/proof, and align with that
benchmark-derived policy. It is shadow-only: it records a verdict and never changes
production routing (honouring the PR20 active gate).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.model_forge.capability_scoring import build_capability_profile
from agent.model_forge.execution_policy import ExecutionPolicySelector
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeModel, ModelProfile

# Atlas execution phases this validator covers, with their evidence/proof requirements.
PHASE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "planning": {
        "acceptable_status": {"plan_ready", "planned", "plan_pool_ready"},
        "needs_evidence": True,
    },
    "code_development": {
        "acceptable_status": {"patch_proposed", "proposed", "implemented"},
        "needs_evidence": True,
        "aligns_with_optimal_route": True,
    },
    "completion": {
        "acceptable_status": {"verified", "complete", "converged"},
        "needs_evidence": True,
        "needs_verification": True,
        "needs_safe_apply": True,
    },
}


class AtlasPhaseObservation(ForgeModel):
    phase: str
    route: ForgeRoute
    status: str
    evidence_refs: list[str] = []
    verification_proof: bool = False
    safe_apply_proof: bool = False


class AtlasPhaseValidation(ForgeModel):
    phase: str
    valid: bool
    route_within_safe: bool
    route_matches_optimal: bool
    evidence_present: bool
    status_ok: bool
    issues: list[str] = []


class AtlasRouteValidationReport(ForgeModel):
    status: str = "shadow_validation_not_applied"
    run_id: str
    provider_id: str
    model_id: str
    change_class: ChangeClass
    optimal_route: ForgeRoute
    twin_injection_level: int
    method_variant: str = ""
    phases: list[AtlasPhaseValidation]
    overall_valid: bool
    missing_phases: list[str]
    changes_production_routing: bool = False
    proof_level: str
    reasons: list[str] = []


class AtlasRouteValidator:
    def __init__(self, evidence_dir: str | Path, *, route_matrix: RouteMatrix | None = None) -> None:
        self._evidence_dir = Path(evidence_dir)
        self._route_selector = RouteSelector(route_matrix or RouteMatrix())

    def validate(
        self,
        *,
        profile: ModelProfile | None,
        provider_id: str,
        model_id: str,
        change_class: ChangeClass | str,
        observations: list[AtlasPhaseObservation],
        task_category: str = "",
    ) -> AtlasRouteValidationReport:
        change_class = ChangeClass(change_class)
        capability = build_capability_profile(profile, provider_id=provider_id, model_id=model_id)
        policy = ExecutionPolicySelector(route_selector=self._route_selector).select(
            change_class, task_category=task_category, model_profile=capability,
        )
        optimal_route = policy.route
        injection = int(policy.twin_injection_level)

        phases: list[AtlasPhaseValidation] = []
        for obs in observations:
            phases.append(self._validate_phase(obs, change_class, task_category, optimal_route))

        present = {p.phase for p in phases}
        missing = [phase for phase in PHASE_REQUIREMENTS if phase not in present]
        all_valid = bool(phases) and all(p.valid for p in phases)
        overall_valid = all_valid and not missing
        if overall_valid:
            proof_level = "atlas_route_validation_passed"
        elif phases and any(not p.valid for p in phases):
            proof_level = "atlas_route_validation_mismatch"
        else:
            proof_level = "atlas_route_validation_pending"

        report = AtlasRouteValidationReport(
            run_id="atlas_route_" + uuid4().hex[:12],
            provider_id=capability.provider_id,
            model_id=capability.model_id,
            change_class=change_class,
            optimal_route=optimal_route,
            twin_injection_level=injection,
            method_variant=policy.method_variant.value if policy.method_variant else "",
            phases=phases,
            overall_valid=overall_valid,
            missing_phases=missing,
            proof_level=proof_level,
            reasons=[f"missing_phase:{m}" for m in missing],
        )
        return self._write(report)

    def _validate_phase(
        self,
        obs: AtlasPhaseObservation,
        change_class: ChangeClass,
        task_category: str,
        optimal_route: ForgeRoute,
    ) -> AtlasPhaseValidation:
        req = PHASE_REQUIREMENTS.get(obs.phase, {})
        issues: list[str] = []

        selection = self._route_selector.select(
            change_class, task_category=task_category, requested_route=obs.route,
        )
        route_within_safe = (not selection.overridden) and selection.selected_route == obs.route
        if not route_within_safe:
            issues.append(f"route_not_within_safe_candidates:{obs.route.value}")

        route_matches_optimal = obs.route == optimal_route
        if req.get("aligns_with_optimal_route") and not route_matches_optimal:
            issues.append(f"route_off_benchmark_optimal:{obs.route.value}!={optimal_route.value}")

        evidence_present = (not req.get("needs_evidence")) or bool(obs.evidence_refs)
        if not evidence_present:
            issues.append("missing_evidence")

        status_ok = obs.status in req.get("acceptable_status", set())
        if not status_ok:
            issues.append(f"unexpected_status:{obs.status}")

        if req.get("needs_verification") and not obs.verification_proof:
            issues.append("missing_verification_proof")
        if req.get("needs_safe_apply") and not obs.safe_apply_proof:
            issues.append("missing_safe_apply_proof")

        if obs.phase not in PHASE_REQUIREMENTS:
            issues.append(f"unknown_phase:{obs.phase}")

        return AtlasPhaseValidation(
            phase=obs.phase,
            valid=not issues,
            route_within_safe=route_within_safe,
            route_matches_optimal=route_matches_optimal,
            evidence_present=evidence_present,
            status_ok=status_ok,
            issues=issues,
        )

    def _write(self, report: AtlasRouteValidationReport) -> AtlasRouteValidationReport:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self._evidence_dir / f"{report.run_id}.json"
        path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return report.model_copy(update={"reasons": [*report.reasons, f"report_ref:{path}"]})


__all__ = [
    "AtlasPhaseObservation",
    "AtlasPhaseValidation",
    "AtlasRouteValidationReport",
    "AtlasRouteValidator",
    "PHASE_REQUIREMENTS",
]
