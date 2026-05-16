from pathlib import Path

from agent.atlas_continuation_service import AtlasContinuationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder


def _pool(goal: str = "Ship continuation handoff"):
    pool = AtlasPlanPoolBuilder().build_fallback_pool(root_goal=goal, pool_id="pool_continuation")
    pool.status = "ready"
    pool.current_item_id = pool.items[0].item_id
    return pool


def test_no_workspace_returns_summary(tmp_path) -> None:
    service = AtlasContinuationService(AtlasJournal(tmp_path))

    summary = service.build_latest_summary()

    assert summary.workspace_id == "default"
    assert summary.status == "no_workspace"
    assert summary.continuation_prompt
    assert "Create or select an Atlas plan pool" in summary.continuation_prompt


def test_plan_pool_only_returns_summary(tmp_path) -> None:
    journal = AtlasJournal(tmp_path)
    pool = _pool()
    journal.save_plan_pool(pool)
    journal.write_checkpoint(pool=pool, next_action="Review the generated Atlas PlanPool before starting a dry-run.")

    summary = AtlasContinuationService(journal).build_pool_summary(pool.pool_id)

    assert summary.pool_id == pool.pool_id
    assert summary.current_goal == pool.root_goal
    assert summary.total_items == len(pool.items)
    assert summary.plan_pool_md_path.endswith("plan_pool.md")
    assert summary.checkpoint_md_path.endswith("checkpoint.md")


def test_pipeline_state_and_events_return_summary(tmp_path) -> None:
    journal = AtlasJournal(tmp_path)
    pool = _pool()
    journal.save_plan_pool(pool)
    state = AtlasPipelineRunState(run_id="run_continuation", pool_id=pool.pool_id, status="paused")
    state.current_item_id = pool.items[1].item_id
    state.completed_item_ids = [pool.items[0].item_id]
    state.add_event("pipeline_started", message="Pipeline dry-run started.")
    state.add_event("pipeline_paused", item_id=pool.items[1].item_id, message="Pipeline paused after one item.")
    journal.save_pipeline_state(pool.pool_id, state)
    for event in state.events:
      journal.append_event(pool.pool_id, state.run_id, event)
    journal.write_checkpoint(pool=pool, state=state, next_action="Review paused Atlas pipeline state before continuing.")

    summary = AtlasContinuationService(journal).build_pool_summary(pool.pool_id, state.run_id)

    assert summary.run_id == state.run_id
    assert summary.status == "paused"
    assert summary.completed_count == 1
    assert summary.last_event_type == "pipeline_paused"
    assert summary.events_ndjson_path.endswith("events.ndjson")
    assert summary.state_json_path.endswith("state.json")


def test_current_item_title_is_completed_from_plan_pool(tmp_path) -> None:
    journal = AtlasJournal(tmp_path)
    pool = _pool()
    journal.save_plan_pool(pool)
    state = AtlasPipelineRunState(run_id="run_title", pool_id=pool.pool_id, status="running")
    state.current_item_id = pool.items[0].item_id
    journal.save_pipeline_state(pool.pool_id, state)

    summary = AtlasContinuationService(journal).build_pool_summary(pool.pool_id, state.run_id)

    assert summary.current_item_title == pool.items[0].title


def test_build_prompt_contains_handoff_fields_and_policy(tmp_path) -> None:
    journal = AtlasJournal(tmp_path)
    pool = _pool()
    journal.save_plan_pool(pool)
    summary = AtlasContinuationService(journal).build_pool_summary(pool.pool_id)

    prompt = summary.continuation_prompt

    assert f"Pool ID: {pool.pool_id}" in prompt
    assert "Run ID:" in prompt
    assert "Next Action:" in prompt
    assert "Task = PlanItem" in prompt
    assert "Agent = Autopilot" in prompt
    assert "safe_apply / TestCommand / DebugLoop / DeepResearch" in prompt


def test_checkpoint_excerpt_is_truncated(tmp_path) -> None:
    journal = AtlasJournal(tmp_path)
    pool = _pool()
    journal.save_plan_pool(pool)
    path = journal.write_checkpoint(pool=pool, next_action="x" * 200)
    assert path.exists()

    excerpt = AtlasContinuationService(journal).read_checkpoint_excerpt(pool.pool_id, max_chars=32)

    assert len(excerpt) == 32


def test_service_has_no_runtime_side_effect_tokens() -> None:
    source = Path("agent/atlas_continuation_service.py").read_text(encoding="utf-8")

    for forbidden in ["subprocess", "requests.", "httpx", "run_command(", "safe_apply("]:
        assert forbidden not in source
