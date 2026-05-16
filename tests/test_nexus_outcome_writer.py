from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_nexus_research_schema import AtlasNexusContextPack
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyResult
from agent.debug_loop_schema import AtlasDebugAttempt, AtlasDebugLoopState
from agent.nexus_outcome_schema import AtlasNexusOutcome
from agent.nexus_outcome_writer import NexusOutcomeWriter


def test_write_outcome_journal_only_saves_json_and_markdown(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    writer = NexusOutcomeWriter(journal=journal)
    outcome = AtlasNexusOutcome(
        outcome_type="failure",
        source="manual",
        pool_id="pool_1",
        title="Fix failed import",
        summary="Import failed during verification.",
        root_cause="Missing module import.",
        solution="Add the import.",
        reusable_lesson="Check imports after refactors.",
        related_files=["agent/example.py"],
        tags=["atlas", "manual"],
    )

    result = writer.write_outcome(outcome)

    assert result.journal_saved is True
    assert result.nexus_saved is False
    assert result.status == "saved_with_warnings"
    assert Path(result.json_path).exists()
    assert Path(result.markdown_path).exists()
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "Fix failed import" in markdown
    assert "Import failed during verification." in markdown
    assert "Missing module import." in markdown
    assert "Add the import." in markdown
    assert "Check imports after refactors." in markdown


def test_write_outcome_no_journal_no_nexus_skipped() -> None:
    writer = NexusOutcomeWriter()
    outcome = AtlasNexusOutcome(outcome_type="success", source="manual", title="Done")

    result = writer.write_outcome(outcome)

    assert result.status == "skipped"
    assert result.journal_saved is False
    assert result.nexus_saved is False
    assert "journal_unavailable" in result.warnings
    assert "nexus_client_unavailable" in result.warnings


def test_save_to_nexus_uses_save_outcome() -> None:
    class FakeNexusClient:
        def __init__(self) -> None:
            self.payload = None

        def save_outcome(self, payload):
            self.payload = payload
            return {"record_id": "record_1"}

    client = FakeNexusClient()
    writer = NexusOutcomeWriter(nexus_client=client)
    outcome = AtlasNexusOutcome(outcome_type="success", source="manual", title="Done")

    saved, record_id, warnings = writer.save_to_nexus(outcome)

    assert saved is True
    assert record_id == "record_1"
    assert warnings == []
    assert client.payload["outcome_id"] == outcome.outcome_id


def test_save_to_nexus_fallback_save_memory() -> None:
    class FakeNexusClient:
        def save_memory(self, payload):
            return {"id": f"memory_{payload['outcome_id']}"}

    writer = NexusOutcomeWriter(nexus_client=FakeNexusClient())
    outcome = AtlasNexusOutcome(outcome_type="success", source="manual", title="Done")

    saved, record_id, warnings = writer.save_to_nexus(outcome)

    assert saved is True
    assert record_id == f"memory_{outcome.outcome_id}"
    assert warnings == []


def test_save_to_nexus_handles_exception() -> None:
    class FakeNexusClient:
        def save_outcome(self, payload):
            raise RuntimeError("boom")

    writer = NexusOutcomeWriter(nexus_client=FakeNexusClient())
    outcome = AtlasNexusOutcome(outcome_type="success", source="manual", title="Done")

    saved, record_id, warnings = writer.save_to_nexus(outcome)

    assert saved is False
    assert record_id == ""
    assert any(warning.startswith("nexus_outcome_save_failed: boom") for warning in warnings)


def test_outcome_from_pipeline_state_completed_success() -> None:
    state = AtlasPipelineRunState(run_id="run_1", pool_id="pool_1", status="completed", completed_item_ids=["item_1"])
    pool = AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Goal",
        items=[AtlasPlanItem(item_id="item_1", pool_id="pool_1", title="Item", goal="Do", target_files=["agent/a.py"])],
    )

    outcome = NexusOutcomeWriter().outcome_from_pipeline_state(pool, state)

    assert outcome.outcome_type == "success"
    assert outcome.source == "pipeline"
    assert "completed" in outcome.tags
    assert "agent/a.py" in outcome.related_files


def test_outcome_from_pipeline_state_failed_failure() -> None:
    state = AtlasPipelineRunState(
        run_id="run_1",
        pool_id="pool_1",
        status="failed",
        failed_item_ids=["item_1"],
        errors=["executor_error: failed"],
    )

    outcome = NexusOutcomeWriter().outcome_from_pipeline_state(None, state)

    assert outcome.outcome_type == "failure"
    assert "failed: 1" in outcome.summary
    assert "executor_error: failed" in outcome.summary


def test_outcome_from_debug_attempt() -> None:
    attempt = AtlasDebugAttempt(
        pool_id="pool_1",
        item_id="item_1",
        source_type="pipeline",
        run_id="run_1",
        status="retry_allowed",
        root_cause_category="syntax_error",
        error_summary="SyntaxError on import",
        root_cause="Missing closing parenthesis.",
        proposed_fix="Close the parenthesis.",
        reusable_lesson="Run syntax checks before retrying.",
        related_files=["agent/a.py"],
    )

    outcome = NexusOutcomeWriter().outcome_from_debug_attempt(attempt)

    assert outcome.outcome_type == "debug_lesson"
    assert outcome.root_cause == "Missing closing parenthesis."
    assert outcome.solution == "Close the parenthesis."
    assert outcome.reusable_lesson == "Run syntax checks before retrying."
    assert "syntax_error" in outcome.tags


def test_outcome_from_debug_loop_uses_latest_attempt() -> None:
    first = AtlasDebugAttempt(pool_id="pool_1", source_type="pipeline", status="retry_allowed", root_cause_category="unknown", root_cause="old")
    latest = AtlasDebugAttempt(pool_id="pool_1", source_type="pipeline", status="retry_blocked", root_cause_category="test_failure", root_cause="new")
    loop_state = AtlasDebugLoopState(pool_id="pool_1", attempts=[first, latest])

    outcome = NexusOutcomeWriter().outcome_from_debug_loop(loop_state)

    assert outcome.debug_attempt_id == latest.attempt_id
    assert outcome.outcome_type == "failure"
    assert outcome.root_cause == "new"
    assert len(outcome.metadata["attempts"]) == 2


def test_outcome_from_safe_apply_result_blocked() -> None:
    result = AtlasSafeApplyResult(
        pool_id="pool_1",
        item_id="item_1",
        status="blocked",
        decision="require_approval",
        reasons=["approval is required"],
        categories=["approval_missing"],
    )

    outcome = NexusOutcomeWriter().outcome_from_safe_apply_result(result)

    assert outcome.outcome_type == "failure"
    assert outcome.source == "safe_apply"
    assert "approval" in outcome.solution.lower()
    assert "blocked" in outcome.tags


def test_outcome_from_context_pack() -> None:
    context_pack = AtlasNexusContextPack(
        request_id="request_1",
        purpose="technical_research",
        status="completed_with_warnings",
        summary="Use the existing adapter.",
        recommendations=["Reuse current schema."],
        confidence=0.72,
        warnings=["nexus_empty"],
    )

    outcome = NexusOutcomeWriter().outcome_from_context_pack(context_pack)

    assert outcome.outcome_type == "research_context"
    assert outcome.source == "research"
    assert outcome.context_pack_id == context_pack.context_pack_id
    assert outcome.confidence == 0.72
    assert "Reuse current schema." in outcome.reusable_lesson
    assert "completed_with_warnings" in outcome.tags


def test_writer_has_no_api_db_web_runtime_side_effect_tokens() -> None:
    source = Path("agent/nexus_outcome_writer.py").read_text(encoding="utf-8")

    for forbidden in [
        "FastAPI",
        "@app.",
        "requests.",
        "httpx",
        "subprocess",
        "sqlite3",
        "safe_apply(",
        "run_command(",
        "DeepResearch",
        "deep_research_job",
        ".unlink(",
    ]:
        assert forbidden not in source
