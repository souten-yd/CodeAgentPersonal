"""6th: test verification distinguishes environment problems (pytest/interpreter missing, no tests
collected) from real test failures, and the command runner handles a missing executable gracefully."""
from __future__ import annotations

from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.test_command_runner import TestCommandRunner
from agent.test_command_runner_schema import AtlasTestCommandRequest


class _Res:
    def __init__(self, status="failed", returncode=1, stderr="", stdout="", blocked_reason="", warnings=None):
        self.status = status
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.blocked_reason = blocked_reason
        self.warnings = warnings or []


def _svc():
    return AtlasAutoVerificationService(journal=None, storage=None, command_runner=None)


def test_classify_passed():
    assert _svc()._classify(_Res(status="passed", returncode=0), "pytest_file") == ("passed", [])


def test_classify_real_test_failure_is_failed():
    status, warns = _svc()._classify(_Res(status="failed", returncode=1, stderr="assert 1 == 2"), "pytest_file")
    assert status == "failed"
    assert warns == []


def test_classify_pytest_not_installed_is_blocked_not_failed():
    status, warns = _svc()._classify(_Res(status="failed", returncode=1, stderr="No module named pytest"), "pytest_file")
    assert status == "blocked"
    assert "pytest_not_installed" in warns and "test_harness_unavailable" in warns


def test_classify_no_tests_collected_is_failed_for_regeneration():
    # An empty/placeholder test (pytest exit 5) is a generation defect, not success: it must be a
    # failure so the self-correction loop regenerates a real test (not silently pass/complete).
    status, warns = _svc()._classify(_Res(status="failed", returncode=5, stderr="no tests ran"), "pytest_file")
    assert status == "failed"
    assert "no_tests_collected" in warns


def test_classify_missing_executable_is_blocked():
    status, warns = _svc()._classify(_Res(status="blocked", returncode=None, blocked_reason="executable_not_found"), "pytest_file")
    assert status == "blocked"
    assert "interpreter_or_executable_missing" in warns


def test_runner_missing_executable_blocks_not_fails():
    runner = TestCommandRunner(allowed_commands=["definitely-not-a-real-binary"])
    res = runner.run_command(AtlasTestCommandRequest(command="definitely-not-a-real-binary --version", timeout_seconds=5))
    assert res.status == "blocked"
    assert res.blocked_reason == "executable_not_found"


def test_runner_normalizes_python_to_sys_executable():
    import sys

    runner = TestCommandRunner(allowed_commands=["python -c"])
    # `python -c` is allowlisted only for this test; verify it runs via the active interpreter even
    # if a bare `python` binary is absent from PATH.
    res = runner.run_command(AtlasTestCommandRequest(command="python -c print(123)", timeout_seconds=10))
    assert res.status == "passed", res.stderr
    assert "123" in res.stdout
    assert sys.executable  # sanity


def test_max_failures_default_raised():
    from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest, AtlasMultiItemAutopilotPolicy

    assert AtlasMultiItemAutopilotRequest(pool_id="p").max_failures == 3
    assert AtlasMultiItemAutopilotPolicy(policy_id="x", name="n", description="d").max_failures == 3


def test_harness_provisioner_reports_already_present_when_installed():
    from agent.atlas_test_harness_provisioner import AtlasTestHarnessProvisioner

    p = AtlasTestHarnessProvisioner()
    # pytest is installed in the test interpreter, so ensure_pytest must short-circuit without
    # attempting a network install.
    assert p.pytest_available() is True
    assert p.ensure_pytest()["status"] == "already_present"


def test_harness_provisioner_install_failure_degrades_gracefully(monkeypatch):
    from agent import atlas_test_harness_provisioner as mod

    p = mod.AtlasTestHarnessProvisioner(timeout_seconds=5)
    # Force "missing" so it attempts an install, and make the install fail (e.g. no network).
    monkeypatch.setattr(p, "pytest_available", lambda: False)

    class _Completed:
        returncode = 1
        stderr = "Could not find a version / network unreachable"
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Completed())
    out = p.ensure_pytest()
    assert out["status"] == "failed"
    assert out["reason"] == "pip_install_failed"
