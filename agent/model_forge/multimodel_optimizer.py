"""PR19: Multi-model role assignment.

Evaluate several model profiles together and assign each Forge role
(planner / implementer / verifier / repairer / reviewer) to the best-fit model,
plus a robust fallback model. Selection is constraint-aware (latency / cost /
local_only / privacy) and records per-role required vs missing evidence so an
unmeasured dimension is never silently treated as competence.

This is a non-applying preview: it produces RoleAssignments and an advisory result;
applying a loadout still goes through the existing Forge loadout/cutover flow.
"""
from __future__ import annotations

from agent.model_forge.capability_scoring import build_capability_profile
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeModel, ModelProfile, RoleAssignment
from agent.model_forge.source_policy import SourceMode
from agent.twin_control_plane.contracts import ModelCapabilityMode

# Role -> the capability dimensions that matter for it. Selection scores a model on
# the measured subset; unmeasured dimensions are neutral (0.5) and recorded as missing
# evidence rather than counted as strength.
ROLE_DIMENSIONS: dict[str, list[str]] = {
    "planner": ["impact_analysis", "abstraction_tolerance", "scope_boundary_discipline"],
    "implementer": [
        "structured_output_fidelity",
        "patch_protocol_fidelity",
        "edit_intent_quality",
        "large_file_editing",
    ],
    "verifier": ["evidence_discipline", "contract_preservation", "stale_test_judgment"],
    "repairer": ["repair_discipline", "fallback_recovery"],
    "reviewer": ["evidence_discipline", "contract_preservation"],
}
ROLE_ROUTE: dict[str, ForgeRoute] = {
    "planner": ForgeRoute.SLICED_IMPACT,
    "implementer": ForgeRoute.PATCH_DSL,
    "verifier": ForgeRoute.CRITICAL_GATE,
    "repairer": ForgeRoute.REPAIR_LOOP,
    "reviewer": ForgeRoute.CRITICAL_GATE,
}
# Roles that must never construct a patch.
_REVIEW_ROLES = {"verifier", "reviewer"}
_NEUTRAL = 0.5
_INJECTION_BY_MODE = {
    ModelCapabilityMode.WEAK_LOCAL: 4,
    ModelCapabilityMode.AUDIT_ONLY: 3,
    ModelCapabilityMode.STANDARD: 2,
    ModelCapabilityMode.FRONTIER_ASSISTED: 1,
}


class ModelCandidate(ForgeModel):
    provider_id: str
    model_id: str
    profile: ModelProfile | None = None
    estimated_latency_ms: int = 0
    cost_tier: float = 0.0          # 0.0 cheapest .. 1.0 most expensive
    local_only_safe: bool = True    # False for external providers (e.g. OpenRouter)


class RoleEvidence(ForgeModel):
    role: str
    score: float
    required_dimensions: list[str]
    missing_evidence: list[str]


class MultiModelAssignmentResult(ForgeModel):
    status: str = "preview_not_applied"
    assignments: list[RoleAssignment]
    fallback_model: RoleAssignment | None = None
    role_evidence: list[RoleEvidence]
    constraints: dict
    eligible_models: list[str]
    reasons: list[str]


class MultiModelRoleOptimizer:
    def assign(
        self,
        candidates: list[ModelCandidate],
        *,
        source_mode: SourceMode = SourceMode.LOCAL_ONLY,
        privacy_sensitive: bool = False,
        latency_weight: float = 0.0001,
        cost_weight: float = 0.2,
    ) -> MultiModelAssignmentResult:
        reasons: list[str] = []
        eligible = self._eligible(candidates, source_mode, privacy_sensitive, reasons)
        if not eligible:
            return MultiModelAssignmentResult(
                status="no_eligible_models",
                assignments=[],
                fallback_model=None,
                role_evidence=[],
                constraints=self._constraints(source_mode, privacy_sensitive, latency_weight, cost_weight),
                eligible_models=[],
                reasons=reasons or ["no_eligible_models_for_constraints"],
            )

        max_latency = max((c.estimated_latency_ms for c in eligible), default=0) or 1
        assignments: list[RoleAssignment] = []
        role_evidence: list[RoleEvidence] = []
        for role in ("planner", "implementer", "verifier", "repairer", "reviewer"):
            best, best_score = self._best_for_role(role, eligible, max_latency, latency_weight, cost_weight)
            assignments.append(self._role_assignment(role, best, best_score))
            role_evidence.append(self._role_evidence(role, best))

        fallback = self._most_robust(eligible, max_latency, latency_weight, cost_weight)
        fallback_assignment = self._role_assignment("fallback", fallback, self._role_score("implementer", fallback))

        return MultiModelAssignmentResult(
            assignments=assignments,
            fallback_model=fallback_assignment,
            role_evidence=role_evidence,
            constraints=self._constraints(source_mode, privacy_sensitive, latency_weight, cost_weight),
            eligible_models=[f"{c.provider_id}:{c.model_id}" for c in eligible],
            reasons=reasons,
        )

    # ----- selection -----

    def _eligible(
        self,
        candidates: list[ModelCandidate],
        source_mode: SourceMode,
        privacy_sensitive: bool,
        reasons: list[str],
    ) -> list[ModelCandidate]:
        eligible: list[ModelCandidate] = []
        for candidate in candidates:
            if source_mode == SourceMode.LOCAL_ONLY and not candidate.local_only_safe:
                reasons.append(f"excluded_external_in_local_only:{candidate.provider_id}:{candidate.model_id}")
                continue
            if privacy_sensitive and not candidate.local_only_safe:
                reasons.append(f"excluded_external_privacy_sensitive:{candidate.provider_id}:{candidate.model_id}")
                continue
            eligible.append(candidate)
        return eligible

    def _role_score(self, role: str, candidate: ModelCandidate) -> float:
        scores = candidate.profile.dimension_scores if candidate.profile else {}
        dims = ROLE_DIMENSIONS[role]
        return sum(float(scores.get(dim, _NEUTRAL)) for dim in dims) / len(dims)

    def _objective(
        self, role: str, candidate: ModelCandidate, max_latency: int,
        latency_weight: float, cost_weight: float,
    ) -> float:
        score = self._role_score(role, candidate)
        latency_penalty = latency_weight * candidate.estimated_latency_ms
        cost_penalty = cost_weight * candidate.cost_tier
        return score - latency_penalty - cost_penalty

    def _best_for_role(
        self, role: str, eligible: list[ModelCandidate], max_latency: int,
        latency_weight: float, cost_weight: float,
    ) -> tuple[ModelCandidate, float]:
        ranked = sorted(
            eligible,
            key=lambda c: (
                self._objective(role, c, max_latency, latency_weight, cost_weight),
                # deterministic tie-break: cheaper, then faster, then id.
                -c.cost_tier,
                -c.estimated_latency_ms,
                c.model_id,
            ),
            reverse=True,
        )
        best = ranked[0]
        return best, self._role_score(role, best)

    def _most_robust(
        self, eligible: list[ModelCandidate], max_latency: int,
        latency_weight: float, cost_weight: float,
    ) -> ModelCandidate:
        # The fallback should be the most well-rounded model: maximize the worst role score.
        def worst_role_score(candidate: ModelCandidate) -> float:
            return min(self._role_score(role, candidate) for role in ROLE_DIMENSIONS)

        return sorted(
            eligible,
            key=lambda c: (worst_role_score(c), -c.cost_tier, -c.estimated_latency_ms, c.model_id),
            reverse=True,
        )[0]

    # ----- assignment construction -----

    def _role_assignment(self, role: str, candidate: ModelCandidate, score: float) -> RoleAssignment:
        capability = build_capability_profile(
            candidate.profile, provider_id=candidate.provider_id, model_id=candidate.model_id,
        )
        route = ROLE_ROUTE.get(role, ForgeRoute.PATCH_DSL)
        if role in _REVIEW_ROLES:
            method = MethodVariant.REVIEW_ONLY
            fallbacks: list[MethodVariant] = []
            abstraction = capability.mode == ModelCapabilityMode.WEAK_LOCAL
            reasons = [f"{role}_never_constructs_patch"]
            instruction = None
        else:
            decision = MethodRouter().select(
                route=route, change_class=ChangeClass.MEDIUM, profile=capability,
            )
            method = decision.chain.primary
            fallbacks = [step.method_variant for step in decision.chain.fallbacks]
            reasons = list(decision.reasons)
            instruction = decision.instruction_abstraction_level

        assignment = RoleAssignment(
            assignment_id=f"role:{candidate.provider_id}:{candidate.model_id}:{role}",
            role=role,
            provider_id=candidate.provider_id,
            model_id=candidate.model_id,
            route=route,
            method_variant=method,
            fallback_methods=fallbacks,
            twin_injection_level=self._injection(role, capability.mode),
            confidence=round(min(0.95, max(0.05, score)), 4),
            evidence_refs=list(candidate.profile.evidence_refs) if candidate.profile else [],
            reasons=reasons,
        )
        if instruction is not None:
            assignment = assignment.model_copy(update={"instruction_abstraction_level": instruction})
        return assignment

    def _role_evidence(self, role: str, candidate: ModelCandidate) -> RoleEvidence:
        measured = set(candidate.profile.dimension_scores) if candidate.profile else set()
        required = ROLE_DIMENSIONS[role]
        missing = [dim for dim in required if dim not in measured]
        return RoleEvidence(
            role=role,
            score=round(self._role_score(role, candidate), 4),
            required_dimensions=required,
            missing_evidence=missing,
        )

    @staticmethod
    def _injection(role: str, mode: ModelCapabilityMode) -> int:
        base = _INJECTION_BY_MODE.get(mode, 2)
        if role in _REVIEW_ROLES:
            base = min(4, base + 1)
        return max(0, min(4, base))

    @staticmethod
    def _constraints(
        source_mode: SourceMode, privacy_sensitive: bool,
        latency_weight: float, cost_weight: float,
    ) -> dict:
        return {
            "source_mode": source_mode.value,
            "privacy_sensitive": privacy_sensitive,
            "latency_weight": latency_weight,
            "cost_weight": cost_weight,
        }
