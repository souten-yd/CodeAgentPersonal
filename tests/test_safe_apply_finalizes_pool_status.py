"""Per-item safe-apply must finalize the pool status when all items reach a terminal state.

Without this the pool stayed at running / approval_required after the last item was applied, so a
completed run looked unfinished/failed in the UI.
"""
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService as S


def _pool(status, *statuses):
    return AtlasPlanPool(
        pool_id="p", root_goal="g", status=status,
        items=[AtlasPlanItem(item_id=f"step_{i+1}", pool_id="p", title="t", goal="g", status=st)
               for i, st in enumerate(statuses)],
    )


def test_all_completed_marks_pool_completed():
    pool = _pool("running", "completed", "completed")
    S._maybe_finalize_pool_status(pool)
    assert pool.status == "completed"


def test_approval_required_with_all_completed_becomes_completed():
    pool = _pool("approval_required", "completed")
    S._maybe_finalize_pool_status(pool)
    assert pool.status == "completed"


def test_pending_item_leaves_status_unchanged():
    pool = _pool("running", "completed", "queued")
    S._maybe_finalize_pool_status(pool)
    assert pool.status == "running"


def test_any_failed_marks_completed_with_warnings():
    pool = _pool("running", "completed", "failed")
    S._maybe_finalize_pool_status(pool)
    assert pool.status == "completed_with_warnings"


def test_human_gate_states_are_not_overridden():
    pool = _pool("blocked_safety_review", "completed")
    S._maybe_finalize_pool_status(pool)
    assert pool.status == "blocked_safety_review"


def test_no_items_is_noop():
    pool = AtlasPlanPool(pool_id="p", root_goal="g", status="running", items=[])
    S._maybe_finalize_pool_status(pool)
    assert pool.status == "running"
