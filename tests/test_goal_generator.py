"""Autonomous self-improvement goal generation (deterministic backlog)."""
from __future__ import annotations

from agent.twin_control_plane.goal_generator import generate_improvement_goals


def test_priority_order_red_suite_first():
    goals = generate_improvement_goals(
        failing_tests=["py://tests/test_a.py#test_x"],
        coverage_gaps=["py://agent/m.py#f"],
        todos=[{"ref": "py://agent/m.py#g", "text": "TODO: handle edge case"}],
    )
    kinds = [g.kind for g in goals]
    assert kinds[0] == "fix_failing_test"          # red suite outranks everything
    assert kinds.index("add_coverage") < kinds.index("resolve_todo")
    assert all(goals[i].priority >= goals[i + 1].priority for i in range(len(goals) - 1))


def test_self_protected_goals_are_flagged():
    goals = generate_improvement_goals(coverage_gaps=["py://agent/atlas_safe_apply_adapter.py#apply"])
    assert goals and goals[0].self_protected is True   # a control module -> needs approval to touch


def test_ordinary_target_not_self_protected():
    goals = generate_improvement_goals(coverage_gaps=["py://agent/model_forge/decomposition_policy.py#f"])
    assert goals and goals[0].self_protected is False


def test_dedup_and_cap():
    goals = generate_improvement_goals(
        coverage_gaps=["py://a#f", "py://a#f", "py://b#g"], max_goals=1)
    assert len(goals) == 1


def test_empty_signals_empty_backlog():
    assert generate_improvement_goals() == []
