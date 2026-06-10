"""Atlas Convergence Module (PI-1).

Public surface: the Convergence facade contract, its DTOs, and the disabled-by-default
stub. Convergence compares target vs actual and recommends a bounded next action; it never
mutates the workspace, PlanPool or Blueprint.
"""

from __future__ import annotations

from agent.project_convergence.contracts import (
    PROJECT_CONVERGENCE_CONTRACT_VERSION,
    ConvergenceDecision,
    ConvergenceModule,
    ConvergenceReport,
    ConvergenceRequest,
    ElementConvergenceResult,
)
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_convergence.module import ConvergenceModuleImpl

__all__ = [
    "PROJECT_CONVERGENCE_CONTRACT_VERSION",
    "ConvergenceDecision",
    "ConvergenceModule",
    "ConvergenceReport",
    "ConvergenceRequest",
    "ElementConvergenceResult",
    "DisabledConvergenceModule",
    "ConvergenceModuleImpl",
]
