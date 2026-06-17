"""Tests for the autonomous failure-repair loop (stubbed IO — no real pytest/git/model)."""
from __future__ import annotations

from agent.twin_control_plane.failure_repair_loop import (
    build_repair_goals, make_repair_callables, run_failure_repair,
)
from agent.twin_control_plane.improvement_loop import KEPT, NEEDS_APPROVAL, ROLLED_BACK, SKIPPED

# 6 failures sharing one cause (plan_pool) across two files -> one batchable goal.
_FAILS = [
    ("tests.test_a::test_1", "KeyError: 'plan_pool'"),
    ("tests.test_a::test_2", "KeyError: 'plan_pool'"),
    ("tests.test_a::test_3", "KeyError: 'plan_pool'"),
    ("tests.test_b::test_4", "KeyError: 'plan_pool'"),
    ("tests.test_b::test_5", "KeyError: 'plan_pool'"),
    ("tests.test_b::test_6", "KeyError: 'plan_pool'"),
]


def test_build_goals_one_per_batchable_cluster():
    goals = build_repair_goals(_FAILS)
    assert len(goals) == 1
    g = goals[0]
    assert g.kind == "missing_key" and "plan_pool" in g.goal_id
    assert g.test_files == ["tests/test_a.py", "tests/test_b.py"]
    assert "tests/test_a.py::test_1" in g.test_ids
    assert g.self_protected is False


def test_self_protected_when_touching_control_surface():
    fails = [("agent.twin_control_plane.test_x::t1", "KeyError: 'plan_pool'") for _ in range(5)]
    # node-file derivation maps to agent/twin_control_plane/... -> protected
    goals = build_repair_goals(fails)
    assert goals and goals[0].self_protected is True


def _stub_io(files: dict, *, repair_changes=True, tests_pass=True):
    """In-memory file map + stub repair/test/git callables."""
    state = {"written": {}, "checked_out": []}

    def read_fn(p):
        return state["written"].get(p, files[p])

    def write_fn(p, s):
        state["written"][p] = s

    def repair_fn(src):
        return (src + "\n# repaired", 1) if repair_changes else (src, 0)

    def run_tests_fn(_ids):
        return tests_pass

    def git_checkout_fn(paths):
        for p in paths:
            state["written"].pop(p, None)
            state["checked_out"].append(p)

    return state, read_fn, write_fn, repair_fn, run_tests_fn, git_checkout_fn


def test_repair_kept_when_tests_pass():
    files = {"tests/test_a.py": "assert call()['plan_pool']", "tests/test_b.py": "assert call()['plan_pool']"}
    state, read_fn, write_fn, repair_fn, run_tests_fn, git_checkout_fn = _stub_io(files, tests_pass=True)
    results = run_failure_repair(_FAILS, repair_fn=repair_fn, read_fn=read_fn, write_fn=write_fn,
                                 run_tests_fn=run_tests_fn, git_checkout_fn=git_checkout_fn)
    assert len(results) == 1 and results[0].outcome == KEPT
    assert state["written"]["tests/test_a.py"].endswith("# repaired")
    assert state["checked_out"] == []                 # nothing rolled back


def test_repair_rolled_back_when_tests_fail():
    files = {"tests/test_a.py": "x", "tests/test_b.py": "y"}
    state, read_fn, write_fn, repair_fn, run_tests_fn, git_checkout_fn = _stub_io(files, tests_pass=False)
    results = run_failure_repair(_FAILS, repair_fn=repair_fn, read_fn=read_fn, write_fn=write_fn,
                                 run_tests_fn=run_tests_fn, git_checkout_fn=git_checkout_fn)
    assert results[0].outcome == ROLLED_BACK
    assert set(state["checked_out"]) == {"tests/test_a.py", "tests/test_b.py"}   # reverted


def test_no_change_is_skipped():
    files = {"tests/test_a.py": "x", "tests/test_b.py": "y"}
    _state, read_fn, write_fn, repair_fn, run_tests_fn, git_checkout_fn = _stub_io(files, repair_changes=False)
    results = run_failure_repair(_FAILS, repair_fn=repair_fn, read_fn=read_fn, write_fn=write_fn,
                                 run_tests_fn=run_tests_fn, git_checkout_fn=git_checkout_fn)
    assert results[0].outcome == SKIPPED


def test_assertion_touching_repair_is_refused():
    # a repair that deletes an assertion must not be written (execute produces no change -> SKIPPED)
    files = {"tests/test_a.py": "assert a == 1\nassert b == 2\n", "tests/test_b.py": "assert c == 3\n"}

    def bad_repair(src):
        return (src.replace("assert b == 2\n", ""), 1)   # drops an assertion

    state, read_fn, write_fn, _r, run_tests_fn, git_checkout_fn = _stub_io(files)
    results = run_failure_repair(_FAILS, repair_fn=bad_repair, read_fn=read_fn, write_fn=write_fn,
                                 run_tests_fn=run_tests_fn, git_checkout_fn=git_checkout_fn)
    assert results[0].outcome == SKIPPED                 # assertion gate refused both files
    assert state["written"] == {}
