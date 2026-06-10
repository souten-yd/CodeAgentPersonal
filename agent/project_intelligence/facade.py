"""Atlas Project Intelligence Module — disabled coordinator facade (PI-1).

The preferred Atlas integration surface. It coordinates the Digital Twin, Blueprint and
Convergence facades without touching their private storage (architecture §5.4). PI-1
ships a disabled coordinator that returns safe, explicit, non-fabricated results so that
existing Atlas behavior is unchanged while the rollout flag is off (ADR-PI-017).

Dependency direction (architecture §3): this module depends on the three module facades;
they never depend on it. It is never an execution authority (ADR-PI-003).
"""

from __future__ import annotations

from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_intelligence.contracts import (
    ApplyResultRequest,
    ContextManifest,
    GenerationContextPackage,
    GenerationContextRequest,
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
    PlanningContextPackage,
    PlanningContextRequest,
    PostApplyIntelligenceResult,
    PostVerificationIntelligenceResult,
    PrepareProjectRequest,
    ProgressRequest,
    ProjectIntelligenceState,
    ProjectMode,
    ProjectProgressResult,
    ProjectStateSummary,
    VerificationResultRequest,
)
from agent.project_twin.facade import DisabledDigitalTwinModule


def _diag(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


def _disabled_manifest(project_id: str, workspace_id: str, phase: str, budget: int) -> ContextManifest:
    return ContextManifest(
        manifest_id="disabled",
        project_id=project_id,
        workspace_id=workspace_id,
        phase=phase,
        token_budget=budget,
        used_tokens=0,
        truncated=False,
        rollout_mode="off",
    )


class DisabledProjectIntelligenceModule:
    """Disabled-by-default orchestration facade.

    Holds only the three module facades (no store, no PlanPool, no FastAPI). Every method
    returns an explicit disabled/unavailable result; none fabricate twin revisions,
    blueprints, convergence reports, passed observations or completion.
    """

    rollout_mode = "off"

    def __init__(
        self,
        *,
        digital_twin: DisabledDigitalTwinModule | None = None,
        blueprint: DisabledArchitectureBlueprintModule | None = None,
        convergence: DisabledConvergenceModule | None = None,
    ) -> None:
        # Compose the three facades through their public surface only.
        self._twin = digital_twin or DisabledDigitalTwinModule()
        self._blueprint = blueprint or DisabledArchitectureBlueprintModule()
        self._convergence = convergence or DisabledConvergenceModule()

    def prepare_project(self, request: PrepareProjectRequest) -> ProjectIntelligenceState:
        return ProjectIntelligenceState(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            project_mode=ProjectMode.IMPORTED_UNKNOWN,
            rollout_mode="off",
            twin_readiness="disabled",
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               "project intelligence disabled (rollout off)")],
        )

    def prepare_planning_context(self, request: PlanningContextRequest) -> PlanningContextPackage:
        pid = request.project.project_id
        wid = request.project.workspace_id
        return PlanningContextPackage(
            project_state=ProjectStateSummary(project_id=pid, workspace_id=wid, readiness="disabled"),
            project_mode=ProjectMode.IMPORTED_UNKNOWN,
            context_manifest=_disabled_manifest(pid, wid, "planning", request.token_budget),
        )

    def prepare_generation_context(self, request: GenerationContextRequest) -> GenerationContextPackage:
        pid = request.project.project_id
        wid = request.project.workspace_id
        return GenerationContextPackage(
            project_id=pid,
            workspace_id=wid,
            plan_pool_id=request.plan_pool_id,
            plan_item_id=request.plan_item_id,
            context_manifest=_disabled_manifest(pid, wid, "generation", request.token_budget),
        )

    def record_apply_result(self, request: ApplyResultRequest) -> PostApplyIntelligenceResult:
        return PostApplyIntelligenceResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            accepted=False,
            refresh_requested=False,
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               "project intelligence disabled (rollout off)")],
        )

    def record_verification_result(self, request: VerificationResultRequest) -> PostVerificationIntelligenceResult:
        # Unavailable is never converted to passed (ADR-PI-013): we accept nothing here.
        return PostVerificationIntelligenceResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            accepted=False,
            reconciled=False,
            convergence_requested=False,
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               "project intelligence disabled (rollout off)")],
        )

    def evaluate_progress(self, request: ProgressRequest) -> ProjectProgressResult:
        return ProjectProgressResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            complete=False,
            diagnostics=[_diag(IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE,
                               "project intelligence disabled (rollout off)")],
        )
