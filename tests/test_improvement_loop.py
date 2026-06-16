"""G3 autonomous improvement cycle: select -> guard -> execute -> verify -> rollback."""
from __future__ import annotations

from types import SimpleNamespace

from agent.twin_control_plane.improvement_loop import (
    KEPT, ROLLED_BACK, NEEDS_APPROVAL, SKIPPED, ERROR,
    run_improvement_cycle, run_improvement_backlog,
)


def _goal(gid="g1", self_protected=False):
    return SimpleNamespace(goal_id=gid, self_protected=self_protected, priority=10)


def test_passing_change_is_kept():
    r = run_improvement_cycle(_goal(),
        execute_fn=lambda g: {"changed": True, "changed_files": ["x.py"]},
        verify_fn=lambda g, e: True, rollback_fn=lambda g, e: (_ for _ in ()).throw(AssertionError("must not roll back")))
    assert r.outcome == KEPT and r.changed and r.verified


def test_failing_verification_rolls_back():
    rolled = []
    r = run_improvement_cycle(_goal(),
        execute_fn=lambda g: {"changed": True}, verify_fn=lambda g, e: False,
        rollback_fn=lambda g, e: rolled.append(True))
    assert r.outcome == ROLLED_BACK and r.changed and not r.verified and rolled == [True]


def test_self_protected_needs_approval_and_does_not_execute():
    executed = []
    r = run_improvement_cycle(_goal(self_protected=True),
        execute_fn=lambda g: executed.append(True) or {"changed": True},
        verify_fn=lambda g, e: True, rollback_fn=lambda g, e: None)
    assert r.outcome == NEEDS_APPROVAL and executed == []  # never executed


def test_self_protected_runs_when_approved():
    r = run_improvement_cycle(_goal(self_protected=True),
        execute_fn=lambda g: {"changed": True}, verify_fn=lambda g, e: True,
        rollback_fn=lambda g, e: None, approved=True)
    assert r.outcome == KEPT


def test_no_change_is_skipped():
    r = run_improvement_cycle(_goal(),
        execute_fn=lambda g: {"changed": False}, verify_fn=lambda g, e: True, rollback_fn=lambda g, e: None)
    assert r.outcome == SKIPPED


def test_verify_error_triggers_rollback():
    rolled = []
    r = run_improvement_cycle(_goal(),
        execute_fn=lambda g: {"changed": True},
        verify_fn=lambda g, e: (_ for _ in ()).throw(RuntimeError("boom")),
        rollback_fn=lambda g, e: rolled.append(True))
    assert r.outcome == ROLLED_BACK and rolled == [True]


def test_backlog_runs_bounded_and_approves_by_id():
    goals = [_goal("a"), _goal("b", self_protected=True), _goal("c")]
    res = run_improvement_backlog(goals,
        execute_fn=lambda g: {"changed": True}, verify_fn=lambda g, e: True,
        rollback_fn=lambda g, e: None, max_cycles=3, approved_goal_ids={"b"})
    assert [r.outcome for r in res] == [KEPT, KEPT, KEPT]  # b approved -> runs
    res2 = run_improvement_backlog(goals,
        execute_fn=lambda g: {"changed": True}, verify_fn=lambda g, e: True,
        rollback_fn=lambda g, e: None, max_cycles=1)
    assert len(res2) == 1  # bounded
