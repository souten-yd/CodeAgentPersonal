from pathlib import Path

from agent.atlas_orchestration_summary import AtlasOrchestrationSummaryBuilder
from agent.atlas_pipeline_runner_schema import AtlasPipelineItemResult, AtlasPipelineRunState
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder


def _pool(status: str = "ready"):
    pool = AtlasPlanPoolBuilder().build_fallback_pool(root_goal="Polish orchestration", pool_id="pool_summary")
    pool.status = status
    pool.current_item_id = pool.items[0].item_id
    return pool


def test_no_pool_maps_to_not_started() -> None:
    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(None, None)

    assert summary.phase == "not_started"
    assert summary.next_action == "Create a PlanPool to begin."
    assert summary.can_start_dry_run is False


def test_ready_pool_without_run_can_start_dry_run() -> None:
    pool = _pool("ready")

    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None)

    assert summary.phase == "plan_ready"
    assert summary.can_start_dry_run is True
    assert summary.next_action == "Start Dry-run to validate the PlanPool."


def test_waiting_for_clarification_response_requires_clarification() -> None:
    summary = AtlasOrchestrationSummaryBuilder().build_from_create_plan_response(
        {
            "status": "waiting_for_clarification",
            "questions": [{"question_id": "q1", "prompt": "Need target?"}],
            "warnings": ["needs_user_input"],
        }
    )

    assert summary.phase == "clarification_required"
    assert summary.severity == "warning"
    assert summary.requires_clarification is True
    assert summary.can_start_dry_run is False
    assert summary.metadata["question_count"] == 1


def test_paused_or_approval_required_requires_approval() -> None:
    pool = _pool("ready")
    state = AtlasPipelineRunState(run_id="run_paused", pool_id=pool.pool_id, status="paused")

    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, state)

    assert summary.phase == "approval_required"
    assert summary.requires_approval is True
    assert summary.next_action == "Review approval-required items before continuing."


def test_item_approval_required_requires_approval() -> None:
    pool = _pool("ready")
    state = AtlasPipelineRunState(run_id="run_gate", pool_id=pool.pool_id, status="running")
    state.item_results = [AtlasPipelineItemResult(item_id=pool.items[0].item_id, status="approval_required")]

    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, state)

    assert summary.phase == "approval_required"
    assert summary.requires_approval is True


def test_stale_recovery_can_start_dry_run_when_pool_exists() -> None:
    summary = AtlasOrchestrationSummaryBuilder().build_from_recovery(
        {"status": "stale", "pool_id": "pool_summary", "run_id": "run_missing", "warnings": ["pipeline_state_not_found"]}
    )

    assert summary.phase == "stale_recovery"
    assert summary.is_stale is True
    assert summary.can_start_dry_run is True


def test_completed_is_success_terminal() -> None:
    state = AtlasPipelineRunState(run_id="run_done", pool_id="pool_summary", status="completed")

    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(_pool(), state)

    assert summary.phase == "completed"
    assert summary.severity == "success"
    assert summary.is_terminal is True


def test_failed_is_danger_terminal() -> None:
    state = AtlasPipelineRunState(run_id="run_failed", pool_id="pool_summary", status="failed")

    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(_pool(), state)

    assert summary.phase == "failed"
    assert summary.severity == "danger"
    assert summary.is_terminal is True


def test_blocked_is_danger() -> None:
    state = AtlasPipelineRunState(run_id="run_blocked", pool_id="pool_summary", status="blocked")

    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(_pool(), state)

    assert summary.phase == "blocked"
    assert summary.severity == "danger"
    assert summary.next_action == "Review blocked items and policy/approval reasons."


def test_summary_builder_has_no_execution_side_effect_tokens() -> None:
    source = Path("agent/atlas_orchestration_summary.py").read_text(encoding="utf-8")

    for forbidden in ["subprocess", "requests.", "httpx", "safe_apply(", "TestCommandRunner(", "DebugLoopRunner(", "DeepResearch"]:
        assert forbidden not in source
