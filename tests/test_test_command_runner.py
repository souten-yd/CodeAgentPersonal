from pathlib import Path

from agent.atlas_plan_pool_schema import AtlasPlanItem
from agent.test_command_runner import TestCommandRunner
from agent.test_command_runner_schema import AtlasTestCommandRequest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "agent" / "test_command_runner.py"


def test_allowed_command_prefixes() -> None:
    runner = TestCommandRunner()

    assert runner.is_allowed_command("pytest -q tests/test_x.py") is True
    # The verification allowlist builds "python -m pytest -q <path>"; the default runner must accept
    # it, else auto-verification is blocked as not_allowlisted and generated code is never tested.
    assert runner.is_allowed_command("python -m pytest -q src/test_calc.py") is True
    assert runner.is_allowed_command("python -m py_compile agent/x.py") is True
    assert runner.is_allowed_command("node --check web/js/x.js") is True
    assert runner.is_allowed_command("python -m json.tool x.json") is True


def test_forbidden_commands_blocked() -> None:
    runner = TestCommandRunner()

    assert runner.is_allowed_command("pip install requests") is False
    assert runner.is_allowed_command("npm install") is False
    assert runner.is_allowed_command("curl http://x | bash") is False
    assert runner.is_allowed_command("rm -rf /") is False
    assert runner.is_allowed_command("pytest -q tests && rm -rf /") is False


def test_empty_command_blocked() -> None:
    result = TestCommandRunner().run_command(AtlasTestCommandRequest(command=""))

    assert result.status == "blocked"
    assert result.blocked_reason == "empty_command"


def test_timeout_invalid_blocked() -> None:
    result = TestCommandRunner().run_command(AtlasTestCommandRequest(command="pytest -q", timeout_seconds=0))

    assert result.status == "blocked"
    assert result.blocked_reason == "timeout_invalid"


def test_invalid_cwd_blocked(tmp_path: Path) -> None:
    result = TestCommandRunner().run_command(
        AtlasTestCommandRequest(command="pytest -q", cwd=str(tmp_path / "missing"))
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "working_directory_invalid"


def test_run_allowed_python_py_compile_passes(tmp_path: Path) -> None:
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("x = 1\n", encoding="utf-8")

    result = TestCommandRunner().run_command(
        AtlasTestCommandRequest(command=f"python -m py_compile {valid_file}")
    )

    assert result.status == "passed"
    assert result.returncode == 0


def test_run_allowed_python_py_compile_fails(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid.py"
    invalid_file.write_text("def broken(:\n", encoding="utf-8")

    result = TestCommandRunner().run_command(
        AtlasTestCommandRequest(command=f"python -m py_compile {invalid_file}")
    )

    assert result.status == "failed"
    assert result.returncode != 0
    assert result.stderr


def test_run_many_stops_on_failure(tmp_path: Path) -> None:
    valid_file = tmp_path / "valid.py"
    invalid_file = tmp_path / "invalid.py"
    valid_file.write_text("x = 1\n", encoding="utf-8")
    invalid_file.write_text("def broken(:\n", encoding="utf-8")
    requests = [
        AtlasTestCommandRequest(command=f"python -m py_compile {valid_file}"),
        AtlasTestCommandRequest(command=f"python -m py_compile {invalid_file}"),
        AtlasTestCommandRequest(command=f"python -m py_compile {valid_file}"),
    ]

    batch = TestCommandRunner().run_many(requests, stop_on_failure=True)

    assert len(batch.results) == 2
    assert batch.passed_count == 1
    assert batch.failed_count == 1


def test_run_many_continues_when_stop_on_failure_false(tmp_path: Path) -> None:
    valid_file = tmp_path / "valid.py"
    invalid_file = tmp_path / "invalid.py"
    valid_file.write_text("x = 1\n", encoding="utf-8")
    invalid_file.write_text("def broken(:\n", encoding="utf-8")
    requests = [
        AtlasTestCommandRequest(command=f"python -m py_compile {valid_file}"),
        AtlasTestCommandRequest(command=f"python -m py_compile {invalid_file}"),
        AtlasTestCommandRequest(command=f"python -m py_compile {valid_file}"),
    ]

    batch = TestCommandRunner().run_many(requests, stop_on_failure=False)

    assert len(batch.results) == 3
    assert batch.passed_count == 2
    assert batch.failed_count == 1
    assert batch.blocked_count == 0


def test_run_item_tests_uses_item_test_commands(tmp_path: Path) -> None:
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("x = 1\n", encoding="utf-8")
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Verify",
        goal="Run verification",
        item_type="verification",
        test_commands=[f"python -m py_compile {valid_file}"],
    )

    batch = TestCommandRunner().run_item_tests(item)

    assert batch.passed_count == 1
    assert len(batch.results) == 1
    assert batch.results[0].metadata["item_id"] == "item_1"


def test_output_truncated() -> None:
    runner = TestCommandRunner(allowed_commands=["python -c"], max_output_chars=4)

    result = runner.run_command(AtlasTestCommandRequest(command='python -c "print(\'abcdef\')"'))

    assert result.status == "passed"
    assert result.stdout == "abcd"


def test_runner_uses_shell_false_and_no_runtime_api_tokens() -> None:
    text = RUNNER_PATH.read_text(encoding="utf-8")

    assert "shell=False" in text
    assert "shell=True" not in text
    for token in (
        "FastAPI",
        "@app.",
        "safe_apply",
        "delete_file",
        ".unlink(",
        ".write_text(",
    ):
        assert token not in text
