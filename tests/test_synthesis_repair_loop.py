"""Tests for the end-to-end synthesis repair loop (stubbed IO/LLM — no real model/pytest/git)."""
from __future__ import annotations

from agent.twin_control_plane.improvement_loop import KEPT, NEEDS_APPROVAL, ROLLED_BACK, SKIPPED
from agent.twin_control_plane.cause_discovery import CauseOrigin
from agent.twin_control_plane.synthesis_repair_loop import repair_one

_TEST = "import subject as s\n\ndef test_add():\n    assert s.add(2, 3) == 5\n"
_BUGGY = "def add(a, b):\n    return a - b\n"
_FIXED = "def add(a, b):\n    return a + b\n"


def _io(files, *, tests_pass_after_fix=True):
    state = {"w": dict(files), "checked_out": [], "ran": []}

    def read(p): return state["w"][p]
    def write(p, s): state["w"][p] = s
    def git_checkout(p): state["checked_out"].append(p); state["w"][p] = files[p]
    def run_test(nid):
        state["ran"].append(nid)
        return tests_pass_after_fix and "a + b" in state["w"].get("agent/subject.py", "")
    return state, read, write, run_test, git_checkout


def _llm_fix(system, user):
    return {"function": _FIXED}


def test_kept_when_synthesis_fixes(tmp_path):
    files = {"tests/test_subject.py": _TEST, "agent/subject.py": _BUGGY}
    state, read, write, run_test, git_checkout = _io(files)
    r = repair_one("tests/test_subject.py::test_add", "assert 5 == 5", llm_json_fn=_llm_fix,
                   include=("agent/",), read_fn=read, write_fn=write, run_test_fn=run_test,
                   git_checkout_fn=git_checkout, localize_fn=lambda src,tn:[CauseOrigin("add","agent/subject.py",1,"add")])
    assert r.outcome == KEPT and r.func == "add"
    assert "a + b" in state["w"]["agent/subject.py"]
    assert state["checked_out"] == []


def test_rolled_back_when_fix_does_not_pass(tmp_path):
    files = {"tests/test_subject.py": _TEST, "agent/subject.py": _BUGGY}
    state, read, write, run_test, git_checkout = _io(files, tests_pass_after_fix=False)
    r = repair_one("tests/test_subject.py::test_add", "x", llm_json_fn=_llm_fix, include=("agent/",),
                   read_fn=read, write_fn=write, run_test_fn=run_test, git_checkout_fn=git_checkout, localize_fn=lambda src,tn:[CauseOrigin("add","agent/subject.py",1,"add")])
    assert r.outcome == ROLLED_BACK
    assert "agent/subject.py" in state["checked_out"]            # reverted


def test_skipped_when_no_function_localized():
    files = {"tests/test_subject.py": "def test_x():\n    assert 1 == 1\n", "agent/subject.py": _BUGGY}
    _state, read, write, run_test, git_checkout = _io(files)
    r = repair_one("tests/test_subject.py::test_x", "x", llm_json_fn=_llm_fix, include=("agent/",),
                   read_fn=read, write_fn=write, run_test_fn=run_test, git_checkout_fn=git_checkout, localize_fn=lambda src,tn:[])
    assert r.outcome == SKIPPED


def test_needs_approval_for_control_surface():
    test = "import m\n\ndef test_c():\n    assert m.run_improvement_cycle() == 1\n"
    files = {"tests/test_x.py": test,
             "agent/twin_control_plane/improvement_loop.py": "def run_improvement_cycle():\n    return 0\n"}
    _state, read, write, run_test, git_checkout = _io(files)
    r = repair_one("tests/test_x.py::test_c", "x", llm_json_fn=_llm_fix,
                   include=("agent/",), read_fn=read, write_fn=write, run_test_fn=run_test,
                   git_checkout_fn=git_checkout, localize_fn=lambda src,tn:[CauseOrigin("run_improvement_cycle","agent/twin_control_plane/improvement_loop.py",1,"run_improvement_cycle")])
    assert r.outcome == NEEDS_APPROVAL          # never auto-edit the control surface


def test_not_reproduced_when_test_passes_in_isolation():
    # the #1933 false-positive class: the test passes clean -> nothing to fix, never "kept"
    from agent.twin_control_plane.synthesis_repair_loop import NOT_REPRODUCED
    files = {"tests/test_subject.py": _TEST, "agent/subject.py": _FIXED}   # already-correct code
    state, read, write, run_test, gitco = _io(files, tests_pass_after_fix=True)
    r = repair_one("tests/test_subject.py::test_add", "x", llm_json_fn=_llm_fix, include=("agent/",),
                   read_fn=read, write_fn=write, run_test_fn=run_test, git_checkout_fn=gitco,
                   localize_fn=lambda src, tn: [CauseOrigin("add", "agent/subject.py", 1, "add")])
    assert r.outcome == NOT_REPRODUCED
    assert state["w"]["agent/subject.py"] == _FIXED       # untouched
