"""Tests for automated cause discovery (deterministic locate; weak-LLM optional, stubbed here)."""
from __future__ import annotations

from agent.twin_control_plane.cause_discovery import (
    CauseOrigin, diagnose, explain_requirement, extract_failure_signals, locate_in_source,
)


def test_extract_warning_tokens():
    sigs = extract_failure_signals("STATUS: blocked WARNINGS: ['patch_content_missing', 'risk_not_low']")
    tokens = {(s.kind, s.token) for s in sigs}
    assert ("warning", "patch_content_missing") in tokens
    assert ("warning", "risk_not_low") in tokens


def test_extract_in_warnings_assertion():
    sigs = extract_failure_signals("assert 'approval_not_approved' in r.json()['warnings']")
    assert any(s.kind == "warning" and s.token == "approval_not_approved" for s in sigs)


def test_extract_exception_and_mismatch():
    sigs = extract_failure_signals("KeyError: 'plan_pool'")
    assert any(s.kind == "exception" and s.token == "plan_pool" for s in sigs)
    sigs2 = extract_failure_signals("AssertionError: assert 'blocked' == 'simulated'")
    # the ACTUAL value ('blocked') is what the code produced -> the thing to trace
    m = [s for s in sigs2 if s.kind == "mismatch"]
    assert m and m[0].token == "blocked" and "simulated" in m[0].detail


def test_locate_in_source(tmp_path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "svc.py").write_text(
        "def check(x):\n    if not x:\n        warnings.append('patch_content_missing')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_svc.py").write_text("assert 'patch_content_missing' in w\n", encoding="utf-8")
    origins = locate_in_source("patch_content_missing", repo_root=str(tmp_path))
    # found in product source, NOT in the test file
    assert len(origins) == 1
    assert origins[0].file == "agent/svc.py" and origins[0].line == 3
    assert "warnings.append" in origins[0].snippet


def test_explain_requirement_deterministic_without_model():
    o = [CauseOrigin("patch_content_missing", "agent/x.py", 59, "if not content: warn(...)")]
    from agent.twin_control_plane.cause_discovery import CauseSignal
    msg = explain_requirement(CauseSignal("warning", "patch_content_missing"), o, llm_json_fn=None)
    assert "agent/x.py:59" in msg


def test_explain_requirement_uses_weak_llm_when_given():
    o = [CauseOrigin("patch_content_missing", "agent/x.py", 59, "if not metadata.get('proposed_content'): warn")]

    def llm(system, user):
        return {"requirement": "metadata must include patch content", "field": "proposed_content"}

    from agent.twin_control_plane.cause_discovery import CauseSignal
    msg = explain_requirement(CauseSignal("warning", "patch_content_missing"), o, llm_json_fn=llm)
    assert "patch content" in msg and "proposed_content" in msg


def test_diagnose_ranks_located_first():
    def locate_fn(token):
        return [CauseOrigin(token, "agent/x.py", 10, "code")] if token == "patch_content_missing" else []

    diags = diagnose(
        "WARNINGS: ['patch_content_missing']\nassert 'blocked' == 'simulated'",
        locate_fn=locate_fn)
    assert diags[0].signal.token == "patch_content_missing"   # located, ranked first
    assert diags[0].located is True
    assert any(not d.located for d in diags)                  # the mismatch had no origin
