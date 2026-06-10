"""Atlas Convergence Module — disabled facade stub (PI-1).

Ships only a safe disabled implementation. When disabled it reports an explicit
``convergence_unavailable`` diagnostic and a conservative ``halt_unsafe`` decision; it
never reports completion or convergence from missing evidence (ADR-PI-013). Real matcher,
evaluator and policy arrive in PI-13..PI-15.
"""

from __future__ import annotations

from agent.project_convergence.contracts import (
    ConvergenceDecision,
    ConvergenceDecisionRequest,
    ConvergenceGetRequest,
    ConvergenceReport,
    ConvergenceRequest,
)
from agent.project_intelligence.contracts import (
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
)


def _diag(message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(
        code=IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE,
        message=message,
        severity="info",
    )


class DisabledConvergenceModule:
    """Disabled-by-default Convergence facade holding no store reference."""

    rollout_mode = "off"

    def evaluate(self, request: ConvergenceRequest) -> ConvergenceReport:
        return ConvergenceReport(
            report_id="disabled",
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            blueprint_revision_id=request.blueprint_revision_id,
            actual_twin_revision_id=request.actual_twin_revision_id,
            diagnostics=[_diag("convergence disabled (rollout off)")],
        )

    def decide(self, request: ConvergenceDecisionRequest) -> ConvergenceDecision:
        # Conservative: no completion synthesized when convergence is unavailable.
        return ConvergenceDecision(
            action="halt_unsafe",
            reason_codes=["convergence_unavailable"],
            diagnostics=[_diag("convergence disabled (rollout off)")],
        )

    def get_latest(self, request: ConvergenceGetRequest) -> ConvergenceReport | None:
        return None
