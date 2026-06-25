from pathlib import Path

import pytest

from agent.atlas_run_schema import AtlasRunState
from agent.atlas_run_store import AtlasRunStore


def test_run_store_creates_loads_and_saves_state(tmp_path: Path) -> None:
    store = AtlasRunStore(tmp_path)

    state = store.create_run(pool_id="pool_sc1", workspace_id="default", total_items=2)
    assert state.run_id.startswith("atlas_run_")
    assert state.status == "queued"
    assert state.phase == "queued"

    loaded = store.load_state(state.run_id)
    assert loaded.pool_id == "pool_sc1"
    assert loaded.total_items == 2

    updated = store.patch_state(state.run_id, {"status": "running", "phase": "proposal", "current_item_id": "item_1"})
    assert updated.status == "running"
    assert updated.phase == "proposal"
    assert store.load_state(state.run_id).current_item_id == "item_1"


def test_run_events_append_and_read_after_sequence(tmp_path: Path) -> None:
    store = AtlasRunStore(tmp_path)
    state = store.create_run(pool_id="pool_sc1")

    first = store.append_event(state.run_id, event_type="phase_started", phase="proposal", message="proposal")
    second = store.append_event(state.run_id, event_type="phase_completed", phase="proposal", message="done")

    assert first.sequence == 2
    assert second.sequence == 3
    replay = store.read_events(state.run_id, after_sequence=2)
    assert [event.event_type for event in replay] == ["phase_completed"]


def test_run_store_rejects_invalid_ids(tmp_path: Path) -> None:
    store = AtlasRunStore(tmp_path)

    with pytest.raises(ValueError):
        store.create_run(pool_id="../pool")
    with pytest.raises(ValueError):
        store.create_run(pool_id="pool", workspace_id="bad/workspace")
    with pytest.raises(ValueError):
        store.create_run(pool_id="pool", run_id="bad\\run")


def test_terminal_state_is_not_changed_by_heartbeat_only_patch(tmp_path: Path) -> None:
    store = AtlasRunStore(tmp_path)
    state = store.create_run(pool_id="pool_sc1")
    terminal = store.patch_state(state.run_id, {"status": "completed", "phase": "final_summary"})

    after_heartbeat = store.patch_state(
        state.run_id,
        {"status": "running", "phase": "verification", "current_item_id": "item_after_done"},
        heartbeat_only=True,
    )

    assert after_heartbeat.status == "completed"
    assert after_heartbeat.phase == "final_summary"
    assert after_heartbeat.current_item_id == ""
    assert store.load_state(state.run_id).finished_at == terminal.finished_at


def test_run_state_marks_terminal_finished_at_on_save(tmp_path: Path) -> None:
    store = AtlasRunStore(tmp_path)
    state = store.create_run(pool_id="pool_sc1")
    state.status = "failed"
    store.save_state(state)

    saved = store.load_state(state.run_id)
    assert saved.finished_at
    assert saved.terminal is True
