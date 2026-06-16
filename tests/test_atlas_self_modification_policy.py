"""Self-modification guardrail: an autonomous run must not silently weaken its own safety controls.

Genuine tests with negative controls: protected modules are flagged only when the guard is enabled;
ordinary project files are never flagged; approval flips the decision; the path validator returns
``self_protected_path`` only under the guard.
"""
from __future__ import annotations

from agent.atlas_self_modification_policy import (
    classify_self_modification,
    is_self_protected_path,
    resolve_self_modification_guard,
)
from agent.atlas_plan_item_file_changes import validate_protected_relative_path


def test_guard_defaults_off_and_reversible(monkeypatch):
    monkeypatch.delenv("ATLAS_SELF_MODIFICATION_GUARD", raising=False)
    assert resolve_self_modification_guard() is False
    for on in ("1", "on", "true", "yes"):
        monkeypatch.setenv("ATLAS_SELF_MODIFICATION_GUARD", on)
        assert resolve_self_modification_guard() is True


def test_safety_critical_modules_are_self_protected():
    assert is_self_protected_path("agent/atlas_safe_apply_adapter.py")
    assert is_self_protected_path("agent/atlas_approval_service.py")
    assert is_self_protected_path("agent/atlas_full_auto_gate.py")
    assert is_self_protected_path("agent/git_steward/local_adapter.py")  # prefix match
    assert is_self_protected_path("agent/atlas_self_modification_policy.py")  # protects itself
    assert is_self_protected_path("agent\\atlas_safe_apply_adapter.py")  # windows separators


def test_ordinary_files_are_not_self_protected():
    # Negative control: normal product/source files are never self-protected.
    assert not is_self_protected_path("index.html")
    assert not is_self_protected_path("agent/atlas_patch_proposal_service.py")
    assert not is_self_protected_path("src/app.py")
    assert not is_self_protected_path("")


def test_classify_blocks_autonomous_but_allows_approved():
    blocked = classify_self_modification("agent/git_steward/contracts.py", approved=False, guard_enabled=True)
    assert blocked["protected"] and blocked["requires_approval"] and not blocked["allowed_without_approval"]
    assert blocked["reason"] == "self_protected_path_requires_approval"

    approved = classify_self_modification("agent/git_steward/contracts.py", approved=True, guard_enabled=True)
    assert approved["allowed_without_approval"] is True
    assert approved["reason"] == "self_protected_path_approved"


def test_classify_noop_when_guard_disabled():
    d = classify_self_modification("agent/atlas_safe_apply_adapter.py", approved=False, guard_enabled=False)
    assert d["protected"] is False and d["allowed_without_approval"] is True


def test_path_validator_blocks_self_protected_only_under_guard(monkeypatch):
    # Guard off (default): the safety module validates like any other relative path.
    monkeypatch.delenv("ATLAS_SELF_MODIFICATION_GUARD", raising=False)
    ok, reason, _ = validate_protected_relative_path("agent/atlas_safe_apply_adapter.py")
    assert ok is True and reason == ""

    # Guard on: it is blocked as self_protected_path.
    monkeypatch.setenv("ATLAS_SELF_MODIFICATION_GUARD", "on")
    ok2, reason2, _ = validate_protected_relative_path("agent/atlas_safe_apply_adapter.py")
    assert ok2 is False and reason2 == "self_protected_path"

    # An ordinary file is still fine under the guard.
    ok3, reason3, _ = validate_protected_relative_path("index.html")
    assert ok3 is True and reason3 == ""
