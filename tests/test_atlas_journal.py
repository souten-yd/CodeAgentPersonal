from __future__ import annotations

from pathlib import Path

import pytest

from agent.atlas_journal import AtlasJournal
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def make_pool(pool_id: str = "pool_1") -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id=pool_id,
        root_goal="Build the Atlas journal foundation",
        status="ready",
        planning_depth="standard",
        automation_level="plan_then_ask",
        execution_strategy="sequential",
        items=[
            AtlasPlanItem(
                item_id="item_1",
                pool_id=pool_id,
                title="Write journal storage",
                goal="Persist Atlas plan pool state",
                status="ready",
                item_type="implementation",
                risk_level="low",
            )
        ],
    )


def make_state(pool_id: str = "pool_1", run_id: str = "run_1", status: str = "running") -> AtlasPipelineRunState:
    state = AtlasPipelineRunState(
        run_id=run_id,
        pool_id=pool_id,
        status=status,
        current_item_id="item_1",
        completed_item_ids=["item_done"],
        failed_item_ids=[],
        blocked_item_ids=[],
    )
    state.add_event("pipeline_started", message="Pipeline started")
    return state


def test_journal_paths_are_under_workspace(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")

    paths = journal.paths(pool_id="pool_1", run_id="run_1")

    assert Path(paths.workspace_dir) == tmp_path / "atlas" / "workspaces" / "ws_1"
    assert Path(paths.plan_pool_dir) == Path(paths.workspace_dir) / "plan_pools" / "pool_1"
    assert Path(paths.pipeline_run_dir) == Path(paths.plan_pool_dir) / "pipeline_runs" / "run_1"
    assert Path(paths.checkpoint_md) == Path(paths.plan_pool_dir) / "checkpoint.md"


def test_rejects_path_traversal_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        AtlasJournal(tmp_path, workspace_id="../x")

    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    with pytest.raises(ValueError):
        journal.plan_pool_dir("../x")
    with pytest.raises(ValueError):
        journal.pipeline_run_dir("pool_1", "../x")


def test_save_plan_pool_writes_json_and_markdown(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    pool = make_pool()

    artifact = journal.save_plan_pool(pool)

    assert Path(artifact.json_path).exists()
    assert Path(artifact.markdown_path).exists()
    markdown = Path(artifact.markdown_path).read_text(encoding="utf-8")
    assert "Pool ID: pool_1" in markdown
    assert "Root Goal: Build the Atlas journal foundation" in markdown
    assert "Write journal storage" in markdown


def test_save_and_load_plan_pool_roundtrip(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    pool = make_pool()

    journal.save_plan_pool(pool)
    loaded = journal.load_plan_pool("pool_1")

    assert loaded.pool_id == pool.pool_id
    assert loaded.root_goal == pool.root_goal
    assert loaded.items[0].item_id == pool.items[0].item_id
    assert loaded.items[0].title == pool.items[0].title


def test_save_pipeline_state_writes_json_and_markdown(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    state = make_state()

    artifact = journal.save_pipeline_state("pool_1", state)

    assert Path(artifact.json_path).exists()
    assert Path(artifact.markdown_path).exists()
    markdown = Path(artifact.markdown_path).read_text(encoding="utf-8")
    assert "Run ID: run_1" in markdown
    assert "Status: running" in markdown


def test_append_and_read_events(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")

    path = journal.append_event("pool_1", "run_1", {"event_type": "pipeline_started", "message": "Started"})
    journal.append_event("pool_1", "run_1", {"event_type": "item_completed", "message": "Done"})

    assert path.exists()
    assert journal.read_events("pool_1", "run_1")[0]["message"] == "Started"
    limited = journal.read_events("pool_1", "run_1", limit=1)
    assert len(limited) == 1
    assert limited[0]["event_type"] == "item_completed"


def test_write_checkpoint_contains_next_action(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    path = journal.write_checkpoint(pool=make_pool(), state=make_state(), next_action="Review the saved checkpoint.")

    markdown = path.read_text(encoding="utf-8")
    assert "## Next Action" in markdown
    assert "Review the saved checkpoint." in markdown


def test_write_next_actions(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")

    path = journal.write_next_actions("pool_1", ["Inspect current item", "Continue pipeline"])

    markdown = path.read_text(encoding="utf-8")
    assert "Inspect current item" in markdown
    assert "Continue pipeline" in markdown


def test_write_final_report(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")

    path = journal.write_final_report("pool_1", "run_1", "Final Report", "All items completed.")

    markdown = path.read_text(encoding="utf-8")
    assert "Final Report" in markdown
    assert "All items completed." in markdown
    assert "generated_at" in markdown


def test_journal_has_no_runtime_api_command_side_effect_tokens() -> None:
    source = Path("agent/atlas_journal.py").read_text(encoding="utf-8")

    for forbidden in ["FastAPI", "@app.", "subprocess", "safe_apply", "run_command(", "delete_file"]:
        assert forbidden not in source


# --- PIBIH-6: impact analysis section in the plan pool markdown ----------------

def test_plan_pool_markdown_renders_impact_section(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    pool = make_pool()
    pool.metadata["plan_item_impact_map"] = {
        "status": "ready",
        "item_count": 1,
        "impacts": [
            {
                "item_id": "item_1",
                "title": "Write journal storage",
                "confidence": "medium",
                "impacted_files": ["agent/atlas_journal.py"],
                "impacted_symbols": ["py://agent/atlas_journal.py#AtlasJournal.save_plan_pool", "route://GET /x"],
                "related_tests": ["tests/test_atlas_journal.py::test_save_plan_pool"],
                "recommended_commands": ["python -m pytest tests/test_atlas_journal.py"],
                "reasons": ["target file changed", "test covers symbol"],
            }
        ],
    }

    markdown = journal.write_plan_pool_markdown(pool).read_text(encoding="utf-8")

    assert "## Impact Analysis" in markdown
    assert "confidence: medium" in markdown
    assert "agent/atlas_journal.py" in markdown
    assert "route://GET /x" in markdown
    assert "Recommended tests: tests/test_atlas_journal.py::test_save_plan_pool" in markdown
    assert "Reasons: target file changed; test covers symbol" in markdown


def test_plan_pool_markdown_shows_uncertainty_when_impact_unavailable(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    pool = make_pool()  # no plan_item_impact_map in metadata

    markdown = journal.write_plan_pool_markdown(pool).read_text(encoding="utf-8")

    assert "## Impact Analysis" in markdown
    # Unknown impact is uncertainty, never "no risk".
    assert "uncertainty" in markdown.lower()
    assert "not as zero risk" in markdown


def test_plan_pool_markdown_unknown_confidence_is_uncertainty_not_no_risk(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    pool = make_pool()
    pool.metadata["plan_item_impact_map"] = {
        "status": "ready",
        "impacts": [{"item_id": "item_1", "title": "x", "confidence": "unknown", "impacted_files": []}],
    }

    markdown = journal.write_plan_pool_markdown(pool).read_text(encoding="utf-8")

    assert "Impacted files: unknown (uncertainty — not zero risk)" in markdown
    assert "confidence: unknown (uncertainty — not zero risk)" in markdown
