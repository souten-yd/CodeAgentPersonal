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

from agent.architecture_blueprint.contracts import ArchitectureBlueprintModule
from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
from agent.project_convergence.contracts import ConvergenceModule
from agent.project_convergence.contracts import ConvergenceDecisionRequest, ConvergenceRequest
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_intelligence.contracts import (
    ApplyResultRequest,
    ContextManifest,
    GenerationContextPackage,
    GenerationContextRequest,
    GapSummary,
    ImpactSummary,
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
    RequirementSummary,
    TestSummary,
    UncertaintySummary,
    VerificationResultRequest,
)
from agent.project_intelligence.project_mode import detect_project_mode
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_intelligence.telemetry import TelemetrySink
from agent.project_twin.facade import (
    DigitalTwinModule,
    DisabledDigitalTwinModule,
    OpenTwinRequest,
    ProjectEventEnvelope,
    RuntimeIngestRequest,
    TwinContextRequest,
)


def _diag(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


class ProjectIntelligenceCoordinator:
    """Rollout-aware ``ProjectIntelligenceModule`` implementation."""

    def __init__(
        self,
        *,
        digital_twin: DigitalTwinModule | None = None,
        blueprint: ArchitectureBlueprintModule | None = None,
        convergence: ConvergenceModule | None = None,
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

    def _detect_project_mode(self, request: PlanningContextRequest) -> ProjectMode:
        try:
            return detect_project_mode(request.project.project_path)
        except Exception:  # noqa: BLE001 - failed mode detection is advisory, not a planning failure.
            return ProjectMode.IMPORTED_UNKNOWN

    def _active_planning(self, request: PlanningContextRequest) -> PlanningContextPackage:
        phase = "planning"
        state = self._twin.open_project(
            OpenTwinRequest(
                project=request.project,
                requested_capabilities=["source_snapshot", "durable_revision", "query", "context"],
                rollout_mode="active",
                correlation_id=request.correlation_id,
            )
        )
        readiness = str(getattr(state.readiness, "value", state.readiness))
        if readiness == "disabled":
            return self._baseline_planning(request, "active")
        project = state.project
        twin_pkg = self._twin.build_context(
            TwinContextRequest(
                project_id=project.project_id,
                workspace_id=project.workspace_id,
                objective=request.objective,
                phase=phase,
                target_refs=list(request.target_refs),
                token_budget=request.token_budget,
            )
        )
        twin_revision_id = twin_pkg.twin_revision_id or state.twin_revision_id
        impacted = [
            ImpactSummary(
                ref=item.ref,
                impacted_refs=list(item.source_refs),
                confidence=float(item.confidence),
            )
            for item in [*twin_pkg.symbols, *twin_pkg.interfaces, *twin_pkg.behavior_paths, *twin_pkg.state_and_events]
        ]
        impacted.extend(
            ImpactSummary(ref=excerpt.ref, impacted_refs=[f"file://{excerpt.path}"], confidence=1.0)
            for excerpt in twin_pkg.source_material
        )
        return PlanningContextPackage(
            project_state=ProjectStateSummary(
                project_id=project.project_id,
                workspace_id=project.workspace_id,
                readiness=readiness,
                twin_revision_id=twin_revision_id,
                available_capabilities=list(state.available_capabilities),
                stale_reasons=list(state.stale_reasons),
            ),
            project_mode=self._detect_project_mode(request),
            actual_twin_revision_id=twin_revision_id,
            requirements=[
                RequirementSummary(requirement_id=item.ref, text=item.summary, status=item.status)
                for item in twin_pkg.requirements
            ],
            impacted_areas=impacted,
            unresolved_gaps=[
                GapSummary(gap_id=item.ref, description=item.summary, mandatory=False, missing_refs=list(item.source_refs))
                for item in twin_pkg.preserve_behaviors
                if item.status in {"missing", "contradicted"}
            ],
            relevant_tests=[
                TestSummary(ref=item.ref, name=item.summary or item.ref, reason=item.inclusion_reason)
                for item in twin_pkg.tests
            ],
            uncertainties=[
                UncertaintySummary(ref=item.ref, reason=item.inclusion_reason or item.summary, severity="warning")
                for item in twin_pkg.uncertainties
            ],
            context_manifest=twin_pkg.manifest,
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
            return self._active_planning(request)
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
        active = self._rollout.phase_active("generation")
        if active and request.success:
            event = ProjectEventEnvelope(
                event_id=request.correlation_id or f"apply:{request.plan_pool_id}:{request.plan_item_id}",
                event_type="safe_apply.completed",
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                source="project_intelligence",
                source_revision=request.new_source_revision,
                correlation_id=request.correlation_id,
                plan_pool_id=request.plan_pool_id,
                plan_item_id=request.plan_item_id,
                payload={
                    "plan_pool_id": request.plan_pool_id,
                    "plan_item_id": request.plan_item_id,
                    "applied_refs": list(request.applied_refs),
                    "new_source_revision": request.new_source_revision,
                    "project_path": request.project.project_path,
                    "changed_paths": [ref[len("file://"):] for ref in request.applied_refs if ref.startswith("file://")],
                },
            )
            result = self._twin.ingest_event(event)
            convergence_report_id = None
            convergence_decision = {}
            convergence_diagnostics: list[IntelligenceDiagnostic] = []
            if result.twin_revision_id:
                try:
                    report = self._convergence.evaluate(
                        ConvergenceRequest(
                            project_id=request.project.project_id,
                            workspace_id=request.project.workspace_id,
                            blueprint_revision_id=request.blueprint_revision_id or "unknown",
                            actual_twin_revision_id=result.twin_revision_id,
                            actual_source_revision_id=request.new_source_revision,
                            changed_refs=list(request.applied_refs),
                        )
                    )
                    convergence_report_id = report.report_id
                    decision = self._convergence.decide(
                        ConvergenceDecisionRequest(
                            project_id=request.project.project_id,
                            workspace_id=request.project.workspace_id,
                            report_id=report.report_id,
                            correlation_id=request.correlation_id,
                        )
                    )
                    convergence_decision = decision.model_dump()
                    convergence_diagnostics.extend(report.diagnostics)
                    convergence_diagnostics.extend(decision.diagnostics)
                except Exception as exc:  # noqa: BLE001 - apply success remains canonical truth.
                    convergence_diagnostics.append(
                        _diag(IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE, f"post-apply convergence failed: {exc}")
                    )
            return PostApplyIntelligenceResult(
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                accepted=result.accepted,
                refresh_requested=True,
                twin_revision_id=result.twin_revision_id,
                convergence_report_id=convergence_report_id,
                convergence_decision=convergence_decision,
                diagnostics=[*result.diagnostics, *convergence_diagnostics],
            )
        return PostApplyIntelligenceResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            accepted=False,
            refresh_requested=active,
            diagnostics=[_diag(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
                               f"rollout mode {self._rollout.mode()}")],
        )

    def record_verification_result(self, request: VerificationResultRequest) -> PostVerificationIntelligenceResult:
        active = self._rollout.phase_active("verification")
        if active:
            ingest = self._twin.ingest_runtime(
                RuntimeIngestRequest(
                    project=request.project,
                    observations=request.observations,
                    correlation_id=request.correlation_id,
                )
            )
            evidence_refs = [ref for obs in request.observations for ref in obs.evidence_refs]
            event = ProjectEventEnvelope(
                event_id=request.correlation_id or f"verification:{request.plan_pool_id}:{request.plan_item_id}",
                event_type="verification.completed",
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                source="project_intelligence",
                source_revision=request.source_revision or request.project.source_revision,
                correlation_id=request.correlation_id,
                plan_pool_id=request.plan_pool_id,
                plan_item_id=request.plan_item_id,
                payload={
                    "verification_id": request.correlation_id or request.plan_item_id,
                    "plan_pool_id": request.plan_pool_id,
                    "plan_item_id": request.plan_item_id,
                    "result": "passed" if request.observations and all(obs.result == "passed" for obs in request.observations) else "observed",
                    "evidence_refs": evidence_refs,
                    "source_revision": request.source_revision or request.project.source_revision,
                    "actual_twin_revision_id": request.actual_twin_revision_id,
                    "plan_pool_revision": request.plan_pool_revision,
                },
            )
            projected = self._twin.ingest_event(event)
            twin_revision_id = projected.twin_revision_id or ingest.twin_revision_id or request.actual_twin_revision_id
            convergence_report_id = None
            convergence_decision = {}
            convergence_diagnostics: list[IntelligenceDiagnostic] = []
            if twin_revision_id:
                try:
                    report = self._convergence.evaluate(
                        ConvergenceRequest(
                            project_id=request.project.project_id,
                            workspace_id=request.project.workspace_id,
                            blueprint_revision_id=request.blueprint_revision_id or "unknown",
                            actual_twin_revision_id=twin_revision_id,
                            actual_source_revision_id=request.source_revision or request.project.source_revision,
                            evidence_revision_id=request.correlation_id or None,
                            verification_refs=evidence_refs,
                            full_evaluation=False,
                        )
                    )
                    convergence_report_id = report.report_id
                    decision = self._convergence.decide(
                        ConvergenceDecisionRequest(
                            project_id=request.project.project_id,
                            workspace_id=request.project.workspace_id,
                            report_id=report.report_id,
                            correlation_id=request.correlation_id,
                        )
                    )
                    convergence_decision = decision.model_dump()
                    convergence_diagnostics.extend(report.diagnostics)
                    convergence_diagnostics.extend(decision.diagnostics)
                except Exception as exc:  # noqa: BLE001 - verification persistence remains canonical.
                    convergence_diagnostics.append(
                        _diag(IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE, f"post-verification convergence failed: {exc}")
                    )
            return PostVerificationIntelligenceResult(
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                accepted=projected.accepted and ingest.ingested_count > 0,
                reconciled=False,
                convergence_requested=bool(convergence_report_id),
                twin_revision_id=twin_revision_id,
                convergence_report_id=convergence_report_id,
                convergence_decision=convergence_decision,
                diagnostics=[*ingest.diagnostics, *projected.diagnostics, *convergence_diagnostics],
            )
        # Unavailable is never converted to passed (ADR-PI-013).
        return PostVerificationIntelligenceResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            accepted=False,
            reconciled=False,
            convergence_requested=False,
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
