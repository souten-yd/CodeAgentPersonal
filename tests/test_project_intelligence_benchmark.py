"""PI-25 final comparative benchmark and legacy retirement tests.

- benchmark uses identical constraints for both arms;
- improvement is demonstrated via the metric table;
- retirement is gated on all PI-25 conditions;
- the Definition-of-Done gate marks COMPLETE only when every gate passes, reporting
  pending live-evidence gates truthfully (never fabricated as passed).
"""

from __future__ import annotations

import pytest

from agent.project_intelligence.benchmark import (
    BenchmarkArm,
    BenchmarkConstraints,
    DoDGate,
    evaluate_definition_of_done,
    retirement_decision,
    run_comparative,
)
from agent.project_intelligence.consolidation import Consumer, ConsumerRegistry, shadow_compare
from agent.project_intelligence.hardening import RegressionBudget


def _constraints():
    return BenchmarkConstraints(model="claude", repository="repo@rev", requirement="R1",
                                token_budget=8000, tool_authority="allowlist", retry_limit=3)


# --- Identical constraints enforced ------------------------------------------

def test_benchmark_requires_identical_constraints() -> None:
    legacy = BenchmarkArm("legacy", _constraints(), {"verified_autonomous_completion": 0.5})
    other = BenchmarkConstraints(model="other", repository="repo@rev", requirement="R1",
                                 token_budget=8000, tool_authority="allowlist", retry_limit=3)
    final = BenchmarkArm("final", other, {"verified_autonomous_completion": 0.8})
    with pytest.raises(ValueError):
        run_comparative(legacy, final)


# --- Improvement demonstrated ------------------------------------------------

def test_final_improves_over_legacy() -> None:
    c = _constraints()
    legacy = BenchmarkArm("legacy", c, {
        "verified_autonomous_completion": 0.50, "false_success": 0.20,
        "requirement_coverage": 0.70, "impact_precision": 0.60, "latency_ms": 100.0,
    })
    final = BenchmarkArm("final", c, {
        "verified_autonomous_completion": 0.85, "false_success": 0.05,
        "requirement_coverage": 0.95, "impact_precision": 0.80, "latency_ms": 110.0,
    })
    report = run_comparative(legacy, final)
    assert report.verdict == "improved"
    assert "verified_autonomous_completion" in report.improved_metrics
    assert "false_success" in report.improved_metrics  # lower is better
    assert report.deltas["requirement_coverage"] > 0


def test_regression_without_key_improvement_is_regressed() -> None:
    c = _constraints()
    legacy = BenchmarkArm("legacy", c, {"verified_autonomous_completion": 0.8, "latency_ms": 100.0})
    final = BenchmarkArm("final", c, {"verified_autonomous_completion": 0.8, "latency_ms": 200.0})
    report = run_comparative(legacy, final)
    assert "latency_ms" in report.regressed_metrics
    assert report.verdict == "regressed"


# --- Retirement gated on all conditions --------------------------------------

def test_retirement_requires_all_conditions() -> None:
    reg = ConsumerRegistry()
    reg.register(Consumer("c1", "impact_map"))  # still legacy
    parity = shadow_compare("impact_map", {"x": 1}, {"x": 1})
    ready, reasons = retirement_decision("impact_map", reg, parity, rollback_tested=True,
                                         tests_pass=True, data_migration_ok=True, docs_updated=True)
    assert ready is False and any("legacy consumers remain" in r for r in reasons)

    reg.migrate("c1")
    ready2, reasons2 = retirement_decision("impact_map", reg, parity, rollback_tested=True,
                                           tests_pass=True, data_migration_ok=True, docs_updated=True)
    assert ready2 is True and reasons2 == []


def test_retirement_blocked_without_data_migration_or_docs() -> None:
    reg = ConsumerRegistry()  # zero consumers
    parity = shadow_compare("impact_map", {"x": 1}, {"x": 1})
    ready, reasons = retirement_decision("impact_map", reg, parity, rollback_tested=True,
                                         tests_pass=True, data_migration_ok=False, docs_updated=False)
    assert ready is False
    assert any("data migration" in r for r in reasons)
    assert any("docs" in r for r in reasons)


# --- Definition of Done ------------------------------------------------------

def test_dod_complete_only_when_all_gates_pass() -> None:
    gates_all_pass = [
        DoDGate("facades_present", True, "PI-1 facades"),
        DoDGate("deep_graph", True, "PI-6/7 graphs"),
        DoDGate("blueprint_actual_distinct", True, "PI-10/12"),
        DoDGate("convergence_recovery", True, "PI-13/14"),
        DoDGate("greenfield_e2e", True, "PI-20/22"),
        DoDGate("legacy_consolidated", True, "PI-23"),
        DoDGate("cross_platform_recorded", True, "PI-24 live", requires_live=True),
        DoDGate("safety_unchanged", True, "all packages"),
    ]
    report = evaluate_definition_of_done(gates_all_pass)
    assert report.complete is True and report.executable_complete is True
    assert report.pending_live == []


def test_dod_reports_pending_live_truthfully() -> None:
    gates = [
        DoDGate("facades_present", True, "PI-1"),
        DoDGate("cross_platform_recorded", False, "no live runs yet", requires_live=True),
    ]
    report = evaluate_definition_of_done(gates)
    # Executable gates pass, but the program is NOT complete and the live gap is explicit.
    assert report.executable_complete is True
    assert report.complete is False
    assert "cross_platform_recorded" in report.pending_live


def test_dod_executable_failure_blocks_complete() -> None:
    gates = [DoDGate("facades_present", False, "missing")]
    report = evaluate_definition_of_done(gates)
    assert report.complete is False and report.executable_complete is False
    assert "facades_present" in report.failures
