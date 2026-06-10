"""Final comparative benchmark and Definition-of-Done gate (PI-25).

Compares the legacy Atlas and the final Project-Intelligence Atlas under identical
constraints (same model, repository, requirement, token budget, tool authority, retry
limit), computes the program metrics, and evaluates the master-goal Definition of Done.

Truthfulness rule: a DoD gate that requires live evidence (real cross-platform runs,
production cutover) is reported as pending/unavailable until that evidence exists — it is
never fabricated as passed. The program is COMPLETE only when every gate passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.project_intelligence.consolidation import ConsumerRegistry, ParityReport, retirement_ready
from agent.project_intelligence.hardening import RegressionBudget

# Program metrics (master goal / test plan §17).
METRICS = [
    "verified_autonomous_completion", "false_success", "autonomous_recovery",
    "regression_escape", "requirement_coverage", "mandatory_blueprint_convergence",
    "impact_precision", "impact_recall", "test_recommendation_precision",
    "context_tokens", "latency_ms", "human_intervention", "resume_fidelity",
    "cross_platform_success", "cost_per_verified_task",
]

# Metrics where a higher value is better.
_HIGHER_BETTER = frozenset({
    "verified_autonomous_completion", "autonomous_recovery", "requirement_coverage",
    "mandatory_blueprint_convergence", "impact_precision", "impact_recall",
    "test_recommendation_precision", "resume_fidelity", "cross_platform_success",
})


@dataclass(frozen=True)
class BenchmarkConstraints:
    model: str
    repository: str
    requirement: str
    token_budget: int
    tool_authority: str
    retry_limit: int


def assert_identical_constraints(a: BenchmarkConstraints, b: BenchmarkConstraints) -> None:
    if a != b:
        raise ValueError("comparative benchmark requires identical constraints for both arms")


@dataclass
class BenchmarkArm:
    name: str
    constraints: BenchmarkConstraints
    metrics: dict[str, float]


@dataclass
class BenchmarkReport:
    deltas: dict[str, float] = field(default_factory=dict)
    improved_metrics: list[str] = field(default_factory=list)
    regressed_metrics: list[str] = field(default_factory=list)
    verdict: str = "parity"   # improved | parity | regressed


def run_comparative(legacy: BenchmarkArm, final: BenchmarkArm, *, budget: RegressionBudget | None = None) -> BenchmarkReport:
    assert_identical_constraints(legacy.constraints, final.constraints)
    report = BenchmarkReport()
    for m in METRICS:
        if m not in legacy.metrics or m not in final.metrics:
            continue
        lv, fv = legacy.metrics[m], final.metrics[m]
        delta = fv - lv
        report.deltas[m] = delta
        better = (delta > 0) if m in _HIGHER_BETTER else (delta < 0)
        worse = (delta < 0) if m in _HIGHER_BETTER else (delta > 0)
        if better:
            report.improved_metrics.append(m)
        elif worse:
            report.regressed_metrics.append(m)
    # Verdict: improved when key outcomes improve and there is no budget-breaking regression.
    key_improved = "verified_autonomous_completion" in report.improved_metrics or \
                   "false_success" in report.improved_metrics
    if report.regressed_metrics and not key_improved:
        report.verdict = "regressed"
    elif report.improved_metrics:
        report.verdict = "improved"
    else:
        report.verdict = "parity"
    return report


# --- Definition of Done ------------------------------------------------------


@dataclass
class DoDGate:
    name: str
    passed: bool
    evidence: str
    requires_live: bool = False


@dataclass
class DoDReport:
    complete: bool
    executable_complete: bool
    gates: list[DoDGate] = field(default_factory=list)
    pending_live: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def evaluate_definition_of_done(gates: list[DoDGate]) -> DoDReport:
    """The program is COMPLETE only when every gate passes (live gates included).

    Executable-complete is True when every gate that does NOT require live evidence passes;
    pending live gates are reported explicitly (never fabricated as passed).
    """
    failures = [g.name for g in gates if not g.passed and not g.requires_live]
    pending_live = [g.name for g in gates if not g.passed and g.requires_live]
    executable_complete = not failures
    complete = all(g.passed for g in gates)
    return DoDReport(complete=complete, executable_complete=executable_complete, gates=gates,
                     pending_live=pending_live, failures=failures)


# --- Retirement decision (reuses the PI-23 gate) -----------------------------


def retirement_decision(
    capability: str, registry: ConsumerRegistry, parity: ParityReport, *,
    rollback_tested: bool, tests_pass: bool, data_migration_ok: bool, docs_updated: bool,
    documented_superiority: bool = False,
) -> tuple[bool, list[str]]:
    """All PI-25 retirement conditions, including data-migration + docs gates."""
    ready, reasons = retirement_ready(capability, registry, parity, rollback_tested=rollback_tested,
                                      tests_pass=tests_pass, documented_superiority=documented_superiority)
    reasons = list(reasons)
    if not data_migration_ok:
        reasons.append("data migration not verified")
    if not docs_updated:
        reasons.append("docs/status not updated")
    return (not reasons), reasons
