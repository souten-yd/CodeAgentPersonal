"""Deterministic test triage from test->source coverage — no model required.

Genuine tests with negative controls: each classification fires only on its real condition, and the
result chains into the approval-gated test-management plan.
"""
from __future__ import annotations

from agent.twin_control_plane.coverage_triage import build_coverage_triage
from agent.twin_control_plane.test_management import (
    TestAction, build_test_management_plan,
)


def test_impacted_stale_redundant_and_gap_are_classified():
    coverage = {
        "test://test_a": ["py://mod.py#foo"],            # covers an existing, changed symbol -> impacted
        "test://test_b": ["py://mod.py#bar"],            # covers existing, unchanged -> just present
        "test://test_b2": ["py://mod.py#bar"],           # identical coverage to test_b -> redundant
        "test://test_old": ["py://gone.py#removed"],     # covers only a removed symbol -> stale
    }
    existing = ["py://mod.py#foo", "py://mod.py#bar", "py://mod.py#untested"]
    report = build_coverage_triage(coverage, existing_symbols=existing, changed_symbols=["py://mod.py#foo"])

    assert report.impacted_tests == ["test://test_a"]
    assert report.stale_candidates == ["test://test_old"]
    assert report.redundant_candidates == ["test://test_b2"]  # one of the identical pair kept, other flagged
    assert report.coverage_gaps == ["py://mod.py#untested"]   # no test covers it


def test_no_change_means_nothing_impacted():
    report = build_coverage_triage(
        {"test://t": ["py://mod.py#foo"]}, existing_symbols=["py://mod.py#foo"])
    assert report.impacted_tests == []


def test_chains_into_action_plan_with_approval_gating():
    coverage = {
        "test://imp": ["py://mod.py#foo"],
        "test://stale": ["py://gone.py#x"],
        "test://dupA": ["py://mod.py#bar"],
        "test://dupB": ["py://mod.py#bar"],
    }
    report = build_coverage_triage(coverage, existing_symbols=["py://mod.py#foo", "py://mod.py#bar"],
                                   changed_symbols=["py://mod.py#foo"])
    plan = build_test_management_plan(report)
    assert report.impacted_tests == ["test://imp"]
    # Re-run is autonomous; retire/consolidate require approval (never auto-delete).
    for item in plan.items:
        if item.action in (TestAction.RETIRE, TestAction.CONSOLIDATE):
            assert item.approval_required is True
    assert "test://stale" in plan.refs_for(TestAction.RETIRE)
    assert plan.refs_for(TestAction.CONSOLIDATE)  # the duplicate is a consolidation candidate


def test_empty_coverage_is_safe():
    report = build_coverage_triage({}, existing_symbols=["py://m.py#f"])
    assert report.coverage_gaps == ["py://m.py#f"]  # nothing covers it
    assert report.impacted_tests == [] and report.stale_candidates == []
