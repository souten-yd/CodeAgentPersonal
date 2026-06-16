"""TwinProof test-management plan: classifications -> actionable, approval-gated plan.

Genuine tests with negative controls: each classification maps to its action; destructive actions
(retire/consolidate) always require approval and never run autonomously; an empty report yields no plan
and no directive; a failed impacted test moves from RERUN to UPDATE.
"""
from __future__ import annotations

from types import SimpleNamespace

from agent.twin_control_plane.test_management import (
    TestAction,
    build_test_management_plan,
    render_test_management_directive,
    select_impacted_tests,
)
from agent.twin_control_plane.twinproof import TwinProofReport


def _imp(direct=(), transitive=()):
    def mk(pairs):
        return [SimpleNamespace(canonical_ref=r, confidence=c) for r, c in pairs]
    return SimpleNamespace(direct_impacts=mk(direct), transitive_impacts=mk(transitive), recommended_tests=[])


def test_select_impacted_tests_filters_ranks_and_caps():
    impact = _imp(
        direct=[("py://tests/test_a.py#t1", 1.0), ("py://agent/mod.py#f", 0.9)],  # non-test dropped
        transitive=[("py://tests/test_b.py#t2", 0.7), ("py://tests/test_c.py#t3", 0.3)],  # 0.3 below floor
    )
    sel = select_impacted_tests(impact, top_k=10, min_confidence=0.6)
    refs = [s["test_ref"] for s in sel]
    assert refs == ["py://tests/test_a.py#t1", "py://tests/test_b.py#t2"]  # ranked by confidence, floor applied
    assert all(s["confidence"] >= 0.6 for s in sel)


def test_select_impacted_tests_top_k_bounds_output():
    impact = _imp(direct=[(f"py://tests/test_{i}.py#t", 1.0) for i in range(100)])
    assert len(select_impacted_tests(impact, top_k=20, min_confidence=0.0)) == 20


def test_select_impacted_tests_empty_safe():
    assert select_impacted_tests(None) == []


def _report(**kw) -> TwinProofReport:
    return TwinProofReport(report_id="r", **kw)


def test_classifications_map_to_actions():
    plan = build_test_management_plan(_report(
        impacted_tests=["test://a", "test://b"],
        coverage_gaps=["py://mod.py#untested"],
        flaky_candidates=["test://flaky"],
        stale_candidates=["test://gone"],
        redundant_candidates=["test://dup"],
    ))
    assert set(plan.refs_for(TestAction.RERUN)) == {"test://a", "test://b"}
    assert plan.refs_for(TestAction.ADD_COVERAGE) == ["py://mod.py#untested"]
    assert plan.refs_for(TestAction.QUARANTINE) == ["test://flaky"]
    assert plan.refs_for(TestAction.RETIRE) == ["test://gone"]
    assert plan.refs_for(TestAction.CONSOLIDATE) == ["test://dup"]


def test_destructive_actions_require_approval():
    plan = build_test_management_plan(_report(stale_candidates=["test://gone"], redundant_candidates=["test://dup"]))
    for item in plan.items:
        if item.action in (TestAction.RETIRE, TestAction.CONSOLIDATE):
            assert item.approval_required is True
        else:
            assert item.approval_required is False


def test_failed_impacted_test_moves_to_update():
    plan = build_test_management_plan(
        _report(impacted_tests=["test://a", "test://b"]),
        failed_test_refs=["test://b"],
    )
    assert plan.refs_for(TestAction.RERUN) == ["test://a"]
    assert plan.refs_for(TestAction.UPDATE) == ["test://b"]


def test_empty_report_yields_no_plan_or_directive():
    plan = build_test_management_plan(_report())
    assert plan.is_empty
    assert render_test_management_directive(plan) == ""
    assert build_test_management_plan(None).is_empty


def test_directive_warns_against_unapproved_deletion():
    plan = build_test_management_plan(_report(impacted_tests=["test://a"], stale_candidates=["test://gone"]))
    text = render_test_management_directive(plan)
    assert "Test Management" in text
    assert "REQUIRE APPROVAL" in text
    assert "must stay green" in text
    assert "test://gone" in text


def test_to_dict_counts():
    d = build_test_management_plan(_report(
        impacted_tests=["test://a"], stale_candidates=["test://x", "test://y"])).to_dict()
    assert d["rerun_count"] == 1 and d["retire_count"] == 2
