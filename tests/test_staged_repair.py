"""Tests for staged repair (cheap path first, coverage escalation only on the residual) — stubbed."""
from __future__ import annotations

from agent.twin_control_plane.cause_discovery import CauseOrigin, _functions_covering, localize_by_coverage
from agent.twin_control_plane.staged_repair import run_staged_repair

_TEST = "import subject as s\n\ndef test_add():\n    assert s.add(2, 3) == 5\n"
_BUGGY = "def add(a, b):\n    return a - b\n"
_FIXED_LLM = lambda system, user: {"function": "def add(a, b):\n    return a + b\n"}  # noqa: E731


def _io(files, *, pass_predicate):
    state = {"w": dict(files), "checked_out": []}
    return state, (lambda p: state["w"][p]), (lambda p, s: state["w"].__setitem__(p, s)), \
        (lambda nid: pass_predicate(state)), (lambda p: (state["checked_out"].append(p),
                                                         state["w"].__setitem__(p, files[p])))


def test_functions_covering_maps_lines():
    src = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    assert ("a", 1) in _functions_covering(src, {2})       # line 2 is inside a()
    assert ("b", 4) not in _functions_covering(src, {2})


def test_localize_by_coverage_ranks_fewest_lines_first():
    # stub the coverage runner: two product files executed, the smaller one ranked first
    def run_cov(nid):
        return {"agent/small.py": {2}, "agent/big.py": {2, 3, 4, 5}}

    def read(p):
        return {"agent/small.py": "def leaf():\n    return 1\n",
                "agent/big.py": "def orch():\n    x=1\n    y=2\n    return 3\n"}[p]

    origins = localize_by_coverage("t::x", repo_root="", include=("agent/",),
                                   run_coverage_fn=run_cov, read_fn=read)
    assert origins[0].file == "agent/small.py"             # fewest executed lines first
    assert {o.token for o in origins} == {"leaf", "orch"}


def test_stage_a_fixes_without_touching_coverage():
    files = {"tests/test_subject.py": _TEST, "agent/subject.py": _BUGGY}
    state, read, write, run_test, gitco = _io(files, pass_predicate=lambda s: "a + b" in s["w"]["agent/subject.py"])
    called = {"cov": 0}

    def cov_loc(nid):
        called["cov"] += 1
        return []

    rep = run_staged_repair([("tests/test_subject.py::test_add", "assert 5 == 5")], llm_json_fn=_FIXED_LLM,
                            include=("agent/",), read_fn=read, write_fn=write, run_test_fn=run_test,
                            git_checkout_fn=gitco, localize_fn=lambda src, tn: [CauseOrigin("add", "agent/subject.py", 1, "add")],
                            coverage_localizer=cov_loc)
    s = rep.summary()
    assert s["fixed_stage_a"] == 1 and s["escalated_to_b"] == 0
    assert called["cov"] == 0                               # coverage never paid for — Stage A sufficed


def test_residual_escalates_to_coverage_then_fixes():
    files = {"tests/test_subject.py": _TEST, "agent/subject.py": _BUGGY}
    state, read, write, run_test, gitco = _io(files, pass_predicate=lambda s: "a + b" in s["w"]["agent/subject.py"])

    # Stage A localizer finds nothing -> SKIPPED -> escalate; Stage B (coverage) finds the function
    rep = run_staged_repair([("tests/test_subject.py::test_add", "assert 5 == 5")], llm_json_fn=_FIXED_LLM,
                            include=("agent/",), read_fn=read, write_fn=write, run_test_fn=run_test,
                            git_checkout_fn=gitco, localize_fn=lambda src, tn: [],
                            coverage_localizer=lambda nid: [CauseOrigin("add", "agent/subject.py", 1, "add")])
    s = rep.summary()
    assert s["fixed_stage_a"] == 0
    assert s["escalated_to_b"] == 1
    assert s["fixed_stage_b"] == 1 and s["residual"] == 0


def test_residual_reported_when_both_stages_fail():
    files = {"tests/test_subject.py": _TEST, "agent/subject.py": _BUGGY}
    state, read, write, run_test, gitco = _io(files, pass_predicate=lambda s: False)   # nothing ever passes
    rep = run_staged_repair([("tests/test_subject.py::test_add", "r")], llm_json_fn=_FIXED_LLM,
                            include=("agent/",), read_fn=read, write_fn=write, run_test_fn=run_test,
                            git_checkout_fn=gitco, localize_fn=lambda src, tn: [CauseOrigin("add", "agent/subject.py", 1, "add")],
                            coverage_localizer=lambda nid: [CauseOrigin("add", "agent/subject.py", 1, "add")])
    s = rep.summary()
    assert s["fixed_total"] == 0 and s["residual"] == 1     # the precise human queue
    assert rep.residual[0][0] == "tests/test_subject.py::test_add"
