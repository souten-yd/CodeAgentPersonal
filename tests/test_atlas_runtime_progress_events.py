from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest, AtlasLLMJsonResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path: Path) -> TestClient:
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _create_pool_and_item(client: TestClient) -> tuple[str, str]:
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="Runtime progress item",
        goal="implement runtime progress",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["out.py"],
        metadata={"action_type": "create"},
    )
    pool = AtlasPlanPool(
        pool_id="p1",
        root_goal="runtime progress",
        project_path=str(Path(client.app.state.atlas_ca_data_dir)),
        status="ready",
        items=[item],
    )
    storage = AtlasPlanPoolStorage(Path(client.app.state.atlas_ca_data_dir))
    journal = AtlasJournal(Path(client.app.state.atlas_ca_data_dir), workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return pool.pool_id, item.item_id


def test_journal_persists_progress_events_and_latest_snapshot(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="default")

    first = journal.append_progress_event("p1", "r1", {"event_type": "llm_started", "phase": "planning", "status": "running"})
    second = journal.append_progress_event("p1", "r1", {"event_type": "llm_token_delta", "phase": "planning", "status": "running", "tokens_total": 3})

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert journal.read_progress_events("p1", "r1", after_sequence=1) == [second]
    assert journal.load_latest_progress("p1", "r1")["event_type"] == "llm_token_delta"
    assert journal.progress_events_path("p1", "r1").exists()
    assert journal.latest_progress_path("p1", "r1").exists()


def test_patch_generation_writes_durable_llm_progress_events(tmp_path: Path) -> None:
    class FakeAdapter(AtlasLLMJsonAdapter):
        def generate_json(self, request: AtlasLLMJsonRequest):
            if self.on_progress:
                self.on_progress({"tokens_generated": 5, "last_token_at": "2099-01-01T00:00:00+00:00"})
            return AtlasLLMJsonResult(
                ok=True,
                data={
                    "summary": "progress test",
                    "proposed_fix": "add durable progress",
                    "target_files": ["out.py"],
                    "proposed_content": "# progress\n",
                    "risk_level": "low",
                },
            )

    client = _client(tmp_path)
    client.app.state.atlas_llm_json_fn = FakeAdapter(model="fake-progress-model")
    pool_id, item_id = _create_pool_and_item(client)

    response = client.post(
        "/api/atlas/patch-proposals/generate",
        json={"pool_id": pool_id, "item_id": item_id, "run_id": "r1", "source_type": "plan_item"},
    )

    assert response.status_code == 200, response.text
    events_response = client.get(f"/api/atlas/pipeline/events/{pool_id}/r1", params={"after_sequence": 0})
    assert events_response.status_code == 200
    progress_events = events_response.json()["progress_events"]
    event_types = [event["event_type"] for event in progress_events]
    assert event_types[:3] == ["atlas_run_started", "llm_started", "llm_first_token"]
    assert event_types[-1] == "llm_completed"
    assert progress_events[2]["tokens_total"] == 5
    assert progress_events[2]["item_id"] == item_id
    assert progress_events[2]["model"] == "fake-progress-model"
    assert events_response.json()["latest_progress"]["event_type"] == "llm_completed"

    status_response = client.get("/api/atlas/patch-proposals/status", params={"pool_id": pool_id, "item_id": item_id})
    assert status_response.status_code == 200
    assert status_response.json()["latest_progress"]["run_id"] == "r1"


def test_pipeline_events_endpoint_replays_durable_run_progress(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post("/api/atlas/plan-pools?sync=1", json={"input": "durable runtime progress"}).json()
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()

    response = client.get(
        f"/api/atlas/pipeline/events/{created['pool_id']}/{dry_run['run_id']}",
        params={"after_sequence": 0},
    )

    assert response.status_code == 200
    progress_events = response.json()["progress_events"]
    assert progress_events[0]["event_type"] == "atlas_run_started"
    assert progress_events[0]["workspace_id"] == "default"
    assert progress_events[0]["pool_id"] == created["pool_id"]
    assert progress_events[0]["run_id"] == dry_run["run_id"]
    assert response.json()["latest_progress"]["event_type"] in {"atlas_run_completed", "atlas_run_failed"}

    replay = client.get(
        f"/api/atlas/pipeline/events/{created['pool_id']}/{dry_run['run_id']}",
        params={"after_sequence": progress_events[0]["sequence"]},
    )
    assert [event["sequence"] for event in replay.json()["progress_events"]] == [event["sequence"] for event in progress_events[1:]]
