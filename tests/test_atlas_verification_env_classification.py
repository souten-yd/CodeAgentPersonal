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


def test_classify_no_tests_collected_is_blocked():
    status, warns = _svc()._classify(_Res(status="failed", returncode=5, stderr="no tests ran"), "pytest_file")
    assert status == "blocked"
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
