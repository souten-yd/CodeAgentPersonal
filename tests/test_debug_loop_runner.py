from __future__ import annotations

import json
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_pipeline_runner_schema import AtlasPipelineItemResult, AtlasPipelineRunState
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyResult
from agent.debug_loop_runner import DebugLoopRunner
from agent.debug_loop_schema import AtlasDebugAttempt, AtlasDebugInput
from agent.test_command_runner_schema import AtlasTestCommandBatchResult, AtlasTestCommandResult


def _debug_input(**overrides):
    payload = {
        "pool_id": "pool_1",
        "item_id": "item_1",
        "run_id": "run_1",
        "source_type": "test_command",
    }
    payload.update(overrides)
    return AtlasDebugInput(**payload)


def test_analyze_syntax_error_allows_retry():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(stderr="SyntaxError: invalid syntax"))

    assert attempt.root_cause_category == "syntax_error"
    assert attempt.status == "retry_allowed"
    assert attempt.retry_recommended is True


def test_analyze_import_error_allows_retry():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(stderr="ModuleNotFoundError: No module named 'missing'"))

    assert attempt.root_cause_category == "import_error"
    assert attempt.status == "retry_allowed"
    assert attempt.retry_recommended is True


def test_analyze_test_failure_allows_retry():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(stdout="FAILED tests/test_x.py::test_y AssertionError"))

    assert attempt.root_cause_category == "test_failure"
    assert attempt.status == "retry_allowed"
    assert attempt.retry_recommended is True


def test_analyze_command_blocked_does_not_retry():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(error_summary="command not allowlisted"))

    assert attempt.root_cause_category == "command_blocked"
    assert attempt.status == "retry_blocked"
    assert attempt.retry_recommended is False


def test_analyze_approval_missing_does_not_retry():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(error_summary="requires approval before retry"))

    assert attempt.root_cause_category == "approval_missing"
    assert attempt.status == "retry_blocked"
    assert attempt.retry_recommended is False


def test_max_retries_reached_blocks_retry():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(stderr="SyntaxError: invalid syntax"), retry_count=2)

    assert attempt.status == "max_retries_reached"
    assert attempt.retry_recommended is False
    assert runner.should_retry(attempt) is False


def test_should_retry_true_for_retry_allowed_under_limit():
    runner = DebugLoopRunner(max_retries=2)
    attempt = runner.analyze_failure(_debug_input(stderr="SyntaxError: invalid syntax"), retry_count=0)

    assert runner.should_retry(attempt) is True


def test_add_attempt_updates_loop_state():
    runner = DebugLoopRunner(max_retries=2)
    loop_state = runner.create_loop_state("pool_1", "item_1", "run_1")
    attempt = AtlasDebugAttempt(
        attempt_id="attempt_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        source_type="manual",
        status="retry_allowed",
        warnings=["warning 1"],
        errors=["error 1"],
    )

    updated = runner.add_attempt(loop_state, attempt)

    assert updated.attempts == [attempt]
    assert updated.status == "retry_allowed"
    assert "warning 1" in updated.warnings
    assert "error 1" in updated.errors


def test_summarize_test_result_from_model():
    runner = DebugLoopRunner()
    result = AtlasTestCommandResult(
        command="pytest -q",
        status="failed",
        returncode=1,
        stdout="out",
        stderr="AssertionError: nope",
    )

    debug_input = runner.summarize_test_result("pool_1", "item_1", "run_1", result)

    assert debug_input.source_type == "test_command"
    assert debug_input.stderr == "AssertionError: nope"
    assert debug_input.status == "failed"
    assert debug_input.returncode == 1
    assert debug_input.metadata["command"] == "pytest -q"


def test_summarize_batch_result_uses_first_failed_result():
    runner = DebugLoopRunner()
    batch = AtlasTestCommandBatchResult(
        results=[
            AtlasTestCommandResult(command="pytest -q tests/test_a.py", status="passed", returncode=0),
            AtlasTestCommandResult(
                command="pytest -q tests/test_b.py",
                status="failed",
                returncode=1,
                stderr="AssertionError: failed item",
            ),
        ],
        passed_count=1,
        failed_count=1,
    )

    debug_input = runner.summarize_batch_result("pool_1", "item_1", "run_1", batch)

    assert debug_input.source_type == "test_command"
    assert debug_input.status == "failed"
    assert debug_input.stderr == "AssertionError: failed item"
    assert debug_input.metadata["command"] == "pytest -q tests/test_b.py"


def test_summarize_safe_apply_result_from_model():
    runner = DebugLoopRunner()
    result = AtlasSafeApplyResult(
        pool_id="pool_1",
        item_id="item_1",
        status="blocked",
        decision="require_approval",
        reasons=["requires approval"],
        categories=["approval_missing"],
    )

    debug_input = runner.summarize_safe_apply_result("pool_1", "item_1", "run_1", result)

    assert debug_input.source_type == "safe_apply"
    assert debug_input.status == "blocked"
    assert debug_input.metadata["decision"] == "require_approval"
    assert "approval_missing" in debug_input.metadata["categories"]


def test_summarize_pipeline_state_from_model():
    runner = DebugLoopRunner()
    state = AtlasPipelineRunState(
        run_id="run_1",
        pool_id="pool_1",
        status="failed",
        failed_item_ids=["item_2"],
        item_results=[
            AtlasPipelineItemResult(item_id="item_2", status="failed", errors=["executor_error: failed"]),
        ],
    )

    debug_input = runner.summarize_pipeline_state("pool_1", state)

    assert debug_input.source_type == "pipeline"
    assert debug_input.status == "failed"
    assert debug_input.run_id == "run_1"
    assert debug_input.item_id == "item_2"
    assert "item_2" in debug_input.metadata["failed_item_ids"]


def test_write_debug_notes_with_journal(tmp_path):
    journal = AtlasJournal(root_dir=tmp_path, workspace_id="workspace_1")
    runner = DebugLoopRunner(journal=journal)
    loop_state = runner.create_loop_state("pool_1", "item_1", "run_1")
    attempt = AtlasDebugAttempt(
        attempt_id="attempt_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        source_type="test_command",
        status="retry_allowed",
        root_cause="A syntax error was found.",
        proposed_fix="Fix the invalid syntax.",
        reusable_lesson="Run syntax checks.",
    )
    runner.add_attempt(loop_state, attempt)

    path = runner.write_debug_notes(loop_state)

    assert path is not None
    assert path.exists()
    markdown = path.read_text(encoding="utf-8")
    assert "A syntax error was found." in markdown
    assert "Fix the invalid syntax." in markdown
    events_path = tmp_path / "atlas" / "workspaces" / "workspace_1" / "plan_pools" / "pool_1" / "pipeline_runs" / "run_1" / "events.ndjson"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event_type"] == "debug_attempt_recorded"


def test_write_debug_notes_without_journal_returns_none():
    runner = DebugLoopRunner(journal=None)
    loop_state = runner.create_loop_state("pool_1", "item_1", "run_1")

    assert runner.write_debug_notes(loop_state) is None


def test_debug_loop_runner_has_no_runtime_api_apply_command_side_effect_tokens():
    text = Path("agent/debug_loop_runner.py").read_text(encoding="utf-8")

    forbidden_tokens = [
        "FastAPI",
        "@app.",
        "subprocess",
        "safe_apply(",
        "run_command(",
        "delete_file",
        "ImplementationExecutor(",
        "TestCommandRunner(",
        ".unlink(",
    ]
    assert not [token for token in forbidden_tokens if token in text]
