from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.atlas_runs as atlas_runs_api
from app.api.atlas_runs import router
from agent.atlas_run_store import AtlasRunStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_retry_failed_run_starts_backend_resume(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_cs9", "run_id": "run_cs9"}).json()["run_id"]
    store = AtlasRunStore(tmp_path)
    store.patch_state(
        run_id,
        {
            "status": "failed",
            "phase": "proposal",
            "current_item_id": "item_1",
            "failed_item_ids": ["item_1"],
            "requires_user_action": True,
            "next_actions": ["retry_or_revise"],
        },
    )

    seen: dict[str, object] = {}

    class FakeOrchestrator:
        def run_items(self, request):
            seen["mode"] = request.mode
            seen["item_ids"] = list(request.item_ids)
            local_store = AtlasRunStore(tmp_path)
            state = local_store.patch_state(
                request.run_id,
                {
                    "status": "completed",
                    "phase": "final_summary",
                    "completed_item_ids": ["item_1"],
                    "failed_item_ids": [],
                    "requires_user_action": False,
                    "next_actions": [],
                },
            )
            local_store.append_event(request.run_id, event_type="run_completed", phase=state.phase, status=state.status)
            return state

    monkeypatch.setattr(atlas_runs_api, "_build_run_orchestrator", lambda request, workspace_id: FakeOrchestrator())

    retry = client.post(f"/api/atlas/runs/{run_id}/retry", json={"reason": "try again"})

    assert retry.status_code == 200
    data = retry.json()
    assert data["execution_started"] is True
    assert data["deferred"] is False
    assert data["reason"] == "retry_started"
    assert seen == {"mode": "resume", "item_ids": []}
    status = client.get(f"/api/atlas/runs/{run_id}/status").json()
    assert status["status"] == "completed"
    state = client.get(f"/api/atlas/runs/{run_id}").json()["state"]
    assert state["retry_count"] == 1
    assert state["last_retry_reason"] == "try again"
    events = client.get(f"/api/atlas/runs/{run_id}/events", params={"after_sequence": 1}).json()["events"]
    event_types = [event["event_type"] for event in events]
    assert "run_lease_acquired" in event_types
    assert event_types.index("run_retry_requested") < event_types.index("run_retry_started")
    assert "run_completed" in event_types
    assert event_types[-1] == "run_lease_released"


def test_retry_budget_is_enforced(client: TestClient, tmp_path: Path) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_cs9_budget"}).json()["run_id"]
    AtlasRunStore(tmp_path).patch_state(
        run_id,
        {"status": "failed", "phase": "proposal", "retry_count": 1, "max_retries": 1, "failed_item_ids": ["item_1"]},
    )

    retry = client.post(f"/api/atlas/runs/{run_id}/retry", json={"reason": "again"})

    assert retry.status_code == 409
    assert retry.json()["detail"]["error"] == "retry_budget_exhausted"


def test_completed_retry_requires_explicit_rerun(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_cs9_done"}).json()["run_id"]
    AtlasRunStore(tmp_path).patch_state(run_id, {"status": "completed", "phase": "final_summary", "completed_item_ids": ["item_1"]})

    rejected = client.post(f"/api/atlas/runs/{run_id}/retry", json={"reason": "again"})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["error"] == "run_completed"

    class FakeOrchestrator:
        def run_items(self, request):
            local_store = AtlasRunStore(tmp_path)
            state = local_store.patch_state(request.run_id, {"status": "completed", "phase": "final_summary"})
            local_store.append_event(request.run_id, event_type="run_completed", phase=state.phase, status=state.status)
            return state

    monkeypatch.setattr(atlas_runs_api, "_build_run_orchestrator", lambda request, workspace_id: FakeOrchestrator())

    accepted = client.post(f"/api/atlas/runs/{run_id}/retry", json={"reason": "rerun", "mode": "rerun"})

    assert accepted.status_code == 200
    assert accepted.json()["execution_started"] is True
    assert accepted.json()["reason"] == "rerun_started"


def test_revise_records_revision_note_without_claiming_execution(client: TestClient) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_cs9_revise"}).json()["run_id"]

    revised = client.post(f"/api/atlas/runs/{run_id}/revise", json={"reason": "make the plan smaller"})

    assert revised.status_code == 200
    data = revised.json()
    assert data["execution_started"] is False
    assert data["deferred"] is False
    assert data["reason"] == "revision_note_recorded"
    assert data["next_actions"] == ["revise_plan"]
    state = client.get(f"/api/atlas/runs/{run_id}").json()["state"]
    assert state["revision_note"] == "make the plan smaller"
    assert state["requires_user_action"] is True
    assert state["next_actions"] == ["revise_plan"]
