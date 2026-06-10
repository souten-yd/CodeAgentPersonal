"""Concrete Convergence facade foundation (PIR-1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.architecture_blueprint.mapping import ActualEntry
from agent.project_convergence.contracts import (
    ConvergenceDecision,
    ConvergenceDecisionRequest,
    ConvergenceGetRequest,
    ConvergenceModule,
    ConvergenceReport,
    ConvergenceRequest,
)
from agent.project_convergence.evaluator import VerificationEvidence, evaluate_convergence
from agent.project_convergence.policy import decide as decide_policy
from agent.project_convergence.store import ConvergenceStore
from agent.project_intelligence.contracts import (
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
)

BlueprintLoader = Callable[[str, str, str], BlueprintRevision | None]
ActualSnapshotLoader = Callable[[str, str, str], list[ActualEntry]]
VerificationLoader = Callable[[str, str, list[str]], dict[str, VerificationEvidence]]


def _diag(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


class ConvergenceModuleImpl(ConvergenceModule):
    """Store-backed Convergence facade.

    The facade persists every report and decision. When no Blueprint/Actual loaders
    are supplied it returns an explicit unavailable diagnostic instead of fabricating
    completion; tests and later production composition can inject real loaders.
    """

    rollout_mode = "concrete"

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        store: ConvergenceStore | None = None,
        blueprint_loader: BlueprintLoader | None = None,
        actual_snapshot_loader: ActualSnapshotLoader | None = None,
        verification_loader: VerificationLoader | None = None,
    ) -> None:
        self._store = store or ConvergenceStore(db_path)
        self._blueprint_loader = blueprint_loader
        self._actual_snapshot_loader = actual_snapshot_loader
        self._verification_loader = verification_loader

    def close(self) -> None:
        self._store.close()

    def _load_blueprint(self, project_id: str, workspace_id: str, revision_id: str) -> BlueprintRevision | None:
        return self._blueprint_loader(project_id, workspace_id, revision_id) if self._blueprint_loader else None

    def evaluate(self, request: ConvergenceRequest) -> ConvergenceReport:
        blueprint = self._load_blueprint(request.project_id, request.workspace_id, request.blueprint_revision_id)
        if blueprint is None or self._actual_snapshot_loader is None:
            report = ConvergenceReport(
                report_id=f"conv:{uuid.uuid4().hex[:10]}",
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                blueprint_revision_id=request.blueprint_revision_id,
                actual_twin_revision_id=request.actual_twin_revision_id,
                diagnostics=[
                    _diag(
                        IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE,
                        "blueprint or actual snapshot loader unavailable",
                    )
                ],
            )
        else:
            snapshot = self._actual_snapshot_loader(
                request.project_id, request.workspace_id, request.actual_twin_revision_id
            )
            verification = (
                self._verification_loader(request.project_id, request.workspace_id, request.verification_refs)
                if self._verification_loader
                else {}
            )
            report = evaluate_convergence(
                blueprint,
                snapshot,
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                twin_revision_id=request.actual_twin_revision_id,
                source_revision_id=request.actual_source_revision_id,
                requirement_revision_id=request.requirement_revision_id,
                mapping_revision_id=request.mapping_revision_id,
                evidence_revision_id=request.evidence_revision_id,
                verification=verification,
            )
        self._store.save_report(
            project_id=report.project_id,
            workspace_id=report.workspace_id,
            blueprint_revision_id=report.blueprint_revision_id,
            report_id=report.report_id,
            payload=report.model_dump(mode="json"),
        )
        return report

    def decide(self, request: ConvergenceDecisionRequest) -> ConvergenceDecision:
        row = self._store.get_report(request.project_id, request.report_id)
        if row is None:
            decision = ConvergenceDecision(
                action="halt_unsafe",
                reason_codes=["report_not_found"],
                diagnostics=[_diag(IntelligenceErrorCode.REVISION_NOT_FOUND, request.report_id)],
            )
        else:
            report = ConvergenceReport.model_validate(row["payload"])
            blueprint = self._load_blueprint(
                report.project_id, report.workspace_id, report.blueprint_revision_id
            )
            if blueprint is None:
                action = "continue" if report.mandatory_gaps or report.element_results else "continue"
                decision = ConvergenceDecision(
                    action=action,
                    reason_codes=["blueprint_unavailable"],
                    mandatory_gaps=[
                        gap.blueprint_element_id for gap in report.mandatory_gaps if gap.blueprint_element_id
                    ],
                    diagnostics=[
                        _diag(
                            IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE,
                            "blueprint unavailable for decision policy",
                        )
                    ],
                )
            else:
                decision = decide_policy(report, blueprint)
        self._store.save_decision(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            report_id=request.report_id,
            decision_id=f"decision:{uuid.uuid4().hex[:10]}",
            payload=decision.model_dump(mode="json"),
        )
        return decision

    def get_latest(self, request: ConvergenceGetRequest) -> ConvergenceReport | None:
        if request.blueprint_revision_id:
            row = self._store.get_latest(request.project_id, request.workspace_id, request.blueprint_revision_id)
        else:
            row = self._store.get_latest_for_workspace(request.project_id, request.workspace_id)
        return ConvergenceReport.model_validate(row["payload"]) if row else None
