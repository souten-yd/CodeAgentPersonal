"""Project Intelligence coordinator (PI-3).

The rollout-aware orchestration facade. It wires the Digital Twin, Blueprint and
Convergence facades (injected) and honours the rollout model:

- off: behaviourally equivalent to the legacy baseline — returns baseline packages, calls
  no module computation, touches no persistence;
- shadow: computes module results for comparison and records telemetry artifacts, but
  returns the baseline package so Planner/Generator inputs are unchanged (ADR-PI-017);
- active (per phase): builds the package from module-facade results.

It depends only on the three module facades and a telemetry sink — never on their private
stores (architecture §3, ADR-PI-015). It is never an execution authority (ADR-PI-003).
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
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_intelligence.telemetry import TelemetrySink
from agent.project_twin.facade import (
    DisabledDigitalTwinModule,
    TwinContextRequest,
)


def _diag(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


class ProjectIntelligenceCoordinator:
    """Rollout-aware ``ProjectIntelligenceModule`` implementation."""

    def __init__(
        self,
        *,
        digital_twin: DisabledDigitalTwinModule | None = None,
        blueprint: DisabledArchitectureBlueprintModule | None = None,
        convergence: DisabledConvergenceModule | None = None,
        rollout: RolloutConfig | None = None,
        telemetry: TelemetrySink | None = None,
    ) -> None:
        self._twin = digital_twin or DisabledDigitalTwinModule()
        self._blueprint = blueprint or DisabledArchitectureBlueprintModule()
        self._convergence = convergence or DisabledConvergenceModule()
        self._rollout = rollout or RolloutConfig.off()
        self._telemetry = telemetry or TelemetrySink()

    @property
    def rollout(self) -> RolloutConfig:
        return self._rollout

    @property
    def telemetry(self) -> TelemetrySink:
        return self._telemetry

    # -- helpers --------------------------------------------------------------

    def _manifest(self, project_id: str, workspace_id: str, phase: str, budget: int, mode: str) -> ContextManifest:
        return ContextManifest(
            manifest_id=f"{mode}:{phase}",
            project_id=project_id,
            workspace_id=workspace_id,
            phase=phase,
            token_budget=budget,
            used_tokens=0,
            truncated=False,
            rollout_mode=mode,
        )

    def _baseline_planning(self, request: PlanningContextRequest, mode: str) -> PlanningContextPackage:
        pid = request.project.project_id
        wid = request.project.workspace_id
        return PlanningContextPackage(
            project_state=ProjectStateSummary(project_id=pid, workspace_id=wid, readiness="disabled"),
            project_mode=ProjectMode.IMPORTED_UNKNOWN,
            context_manifest=self._manifest(pid, wid, "planning", request.token_budget, mode),
        )

    def _baseline_generation(self, request: GenerationContextRequest, mode: str) -> GenerationContextPackage:
        pid = request.project.project_id
        wid = request.project.workspace_id
        return GenerationContextPackage(
            project_id=pid,
            workspace_id=wid,
            plan_pool_id=request.plan_pool_id,
            plan_item_id=request.plan_item_id,
            context_manifest=self._manifest(pid, wid, "generation", request.token_budget, mode),
        )

    def _shadow_compute_and_record(self, request: PlanningContextRequest | GenerationContextRequest, phase: str) -> None:
        """Compute twin context for comparison and record a telemetry artifact only."""
        pid = request.project.project_id
        wid = request.project.workspace_id
        twin_pkg = self._twin.build_context(
            TwinContextRequest(
                project_id=pid, workspace_id=wid, objective="", phase=phase,
                target_refs=list(request.target_refs), token_budget=request.token_budget,
            )
        )
        self._telemetry.record(
            event_type="shadow_comparison",
            phase=phase,
            rollout_mode="shadow",
            project_id=pid,
            workspace_id=wid,
            detail={
                "twin_revision_id": twin_pkg.twin_revision_id,
                "twin_symbol_count": len(twin_pkg.symbols),
                "twin_manifest_id": twin_pkg.manifest.manifest_id,
            },
        )

    # -- facade methods -------------------------------------------------------

    def prepare_project(self, request: PrepareProjectRequest) -> ProjectIntelligenceState:
        mode = self._rollout.mode()
        # Off and shadow report disabled readiness; active still disabled until PI-4 wires
        # the real twin, but the rollout mode is surfaced truthfully.
        return ProjectIntelligenceState(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            project_mode=ProjectMode.IMPORTED_UNKNOWN,
            rollout_mode=mode,
            twin_readiness="disabled",
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               f"project intelligence rollout mode {mode}")],
        )

    def prepare_planning_context(self, request: PlanningContextRequest) -> PlanningContextPackage:
        phase = "planning"
        if self._rollout.phase_active(phase):
            # Active: build from the twin facade (still disabled content until PI-4+),
            # but wired through the public facade and marked active.
            self._twin.build_context(
                TwinContextRequest(project_id=request.project.project_id,
                                   workspace_id=request.project.workspace_id,
                                   phase=phase, target_refs=list(request.target_refs),
                                   token_budget=request.token_budget)
            )
            return self._baseline_planning(request, "active")
        if self._rollout.shadow_active(phase):
            self._shadow_compute_and_record(request, phase)
            return self._baseline_planning(request, "shadow")
        return self._baseline_planning(request, "off")

    def prepare_generation_context(self, request: GenerationContextRequest) -> GenerationContextPackage:
        phase = "generation"
        if self._rollout.phase_active(phase):
            self._twin.build_context(
                TwinContextRequest(project_id=request.project.project_id,
                                   workspace_id=request.project.workspace_id,
                                   phase=phase, target_refs=list(request.target_refs),
                                   token_budget=request.token_budget)
            )
            return self._baseline_generation(request, "active")
        if self._rollout.shadow_active(phase):
            self._shadow_compute_and_record(request, phase)
            return self._baseline_generation(request, "shadow")
        return self._baseline_generation(request, "off")

    def record_apply_result(self, request: ApplyResultRequest) -> PostApplyIntelligenceResult:
        # Off/shadow never accept; active requests a refresh (the real refresh lands in PI-4+).
        active = self._rollout.phase_active("generation")
        return PostApplyIntelligenceResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            accepted=False,
            refresh_requested=active,
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               f"rollout mode {self._rollout.mode()}")],
        )

    def record_verification_result(self, request: VerificationResultRequest) -> PostVerificationIntelligenceResult:
        # Unavailable is never converted to passed (ADR-PI-013).
        return PostVerificationIntelligenceResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            accepted=False,
            reconciled=False,
            convergence_requested=self._rollout.phase_active("verification"),
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               f"rollout mode {self._rollout.mode()}")],
        )

    def evaluate_progress(self, request: ProgressRequest) -> ProjectProgressResult:
        return ProjectProgressResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            complete=False,
            diagnostics=[_diag(IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE,
                               f"rollout mode {self._rollout.mode()}")],
        )
