"""Reproduces a real live-run bug: a plan-pool created under a full_auto preset with an unresolved
non-safety critique finding landed on pool.status == "ready" and stayed there. "ready" has zero
rendering branch in the human-in-the-loop UI (web/js/atlas_claude_panel.js only shows action
controls for approval_required / blocked_safety_review / waiting_for_critical_decision /
clarification-pending), and nothing downstream of plan-pool creation auto-starts a run -- so the
user was stranded on a button-less plan card with no way to approve, revise, or cancel.
"""
from agent.atlas_plan_pool_schema import AtlasPlanPool
from app.api.atlas_pipeline import _promote_ready_pool_for_ui_reachability


def _pool(status: str) -> AtlasPlanPool:
    pool = AtlasPlanPool(pool_id="p1", root_goal="g", project_path="/tmp/repo")
    pool.status = status
    return pool


def test_ready_status_is_promoted_to_approval_required():
    pool = _pool("ready")
    _promote_ready_pool_for_ui_reachability(pool)
    assert pool.status == "approval_required"


def test_non_ready_statuses_are_left_untouched():
    for status in ("needs_scope_confirmation", "approval_required", "waiting_for_critical_decision", "blocked_safety_review", "draft"):
        pool = _pool(status)
        _promote_ready_pool_for_ui_reachability(pool)
        assert pool.status == status


def test_caller_supplied_plan_payload_ready_status_is_left_alone():
    # A plan_payload-supplied pool intentionally bypasses the interactive planner and the UI
    # entirely (e.g. tests, programmatic tooling); "ready" is its correct terminal status.
    pool = _pool("ready")
    _promote_ready_pool_for_ui_reachability(pool, planner_status="skipped")
    assert pool.status == "ready"
