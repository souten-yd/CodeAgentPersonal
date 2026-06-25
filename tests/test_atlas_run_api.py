from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_runs import router
import app.api.atlas_runs as atlas_runs_api
from app.server import create_app
from agent.atlas_run_store import AtlasRunStore


SOURCE = Path("app/api/atlas_runs.py").read_text(encoding="utf-8")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_create_status_and_events_roundtrip(client: TestClient) -> None:
    created = client.post(
        "/api/atlas/runs",
        json={"pool_id": "pool_sc2", "workspace_id": "default", "total_items": 2, "metadata": {"token": "secret"}},
    )

    assert created.status_code == 200
    body = created.json()
    run_id = body["run_id"]
    assert run_id.startswith("atlas_run_")
    assert body["execution_started"] is False
    assert body["state"]["metadata"]["token"] == "[redacted]"

    status = client.get(f"/api/atlas/runs/{run_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "queued"
    assert status.json()["total_items"] == 2

    events = client.get(f"/api/atlas/runs/{run_id}/events")
    assert events.status_code == 200
    event_payload = events.json()
    assert event_payload["events"][0]["event_type"] == "run_created"
    assert event_payload["next_after_sequence"] == 1


def test_decision_endpoint_records_event_without_execution(client: TestClient) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_sc2"}).json()["run_id"]

    decision = client.post(
        f"/api/atlas/runs/{run_id}/decisions",
        json={
            "decision_type": "approve_patch_proposal",
            "decision": "approved",
            "item_id": "item_1",
            "reason": "operator approved",
            "metadata": {"api_key": "do-not-store"},
        },
    )

    assert decision.status_code == 200
    data = decision.json()
    assert data["execution_started"] is False
    assert data["safe_apply_invoked"] is False
    assert data["event"]["event_type"] == "run_decision_recorded"
    assert data["event"]["source"] == "client"
    assert data["event"]["metadata"]["metadata"]["api_key"] == "[redacted]"

    status = client.get(f"/api/atlas/runs/{run_id}/status").json()
    assert status["status"] == "queued"
    assert status["phase"] == "queued"

    after_create = client.get(f"/api/atlas/runs/{run_id}/events", params={"after_sequence": 1}).json()
    assert [event["event_type"] for event in after_create["events"]] == ["run_decision_recorded"]


def test_cancel_marks_run_terminal_and_keeps_event_replay(client: TestClient) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_sc2"}).json()["run_id"]

    cancelled = client.post(f"/api/atlas/runs/{run_id}/cancel", json={"reason": "operator stop"})

    assert cancelled.status_code == 200
    state = cancelled.json()["state"]
    assert state["status"] == "cancelled"
    assert state["phase"] == "final_summary"
    assert state["finished_at"]

    status = client.get(f"/api/atlas/runs/{run_id}/status").json()
    assert status["terminal"] is True
    assert status["block_reason"] == "operator stop"
    events = client.get(f"/api/atlas/runs/{run_id}/events", params={"after_sequence": 1}).json()["events"]
    assert events[-1]["event_type"] == "run_cancel_requested"


def test_revise_records_control_event_without_execution(client: TestClient) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_sc2"}).json()["run_id"]

    revise = client.post(f"/api/atlas/runs/{run_id}/revise", json={"reason": "update plan"}).json()

    assert revise["deferred"] is False
    assert revise["execution_started"] is False
    events = client.get(f"/api/atlas/runs/{run_id}/events", params={"after_sequence": 1}).json()["events"]
    assert [event["event_type"] for event in events] == ["run_revise_requested"]


def test_run_api_rejects_invalid_and_missing_ids(client: TestClient) -> None:
    invalid = client.post("/api/atlas/runs", json={"pool_id": "../pool"})
    missing = client.get("/api/atlas/runs/missing/status")

    assert invalid.status_code == 400
    assert invalid.json()["detail"]["error"] == "invalid_request"
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "run_not_found"


def test_create_run_rejects_duplicate_client_run_id(client: TestClient) -> None:
    first = client.post("/api/atlas/runs", json={"pool_id": "pool_sc2", "run_id": "client_run_1"})
    duplicate = client.post("/api/atlas/runs", json={"pool_id": "pool_sc2", "run_id": "client_run_1"})

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error"] == "run_already_exists"


def test_create_app_registers_run_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())

    created = client.post("/api/atlas/runs", json={"pool_id": "pool_sc2_factory"})

    assert created.status_code == 200
    run_id = created.json()["run_id"]
    assert client.get(f"/api/atlas/runs/{run_id}/status").status_code == 200


def test_start_endpoint_runs_backend_orchestrator(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created = client.post("/api/atlas/runs", json={"pool_id": "pool_sc3", "run_id": "run_sc3"}).json()

    class FakeOrchestrator:
        def run_one_item(self, request):
            store = AtlasRunStore(tmp_path)
            return store.patch_state(
                request.run_id,
                {
                    "status": "completed",
                    "phase": "final_summary",
                    "completed_item_ids": ["item_1"],
                    "current_item_id": "item_1",
                },
            )

    monkeypatch.setattr(atlas_runs_api, "_build_run_orchestrator", lambda request, workspace_id: FakeOrchestrator())

    started = client.post(f"/api/atlas/runs/{created['run_id']}/start", json={"item_id": "item_1"})

    assert started.status_code == 200
    assert started.json()["execution_started"] is True
    status = client.get(f"/api/atlas/runs/{created['run_id']}/status").json()
    assert status["status"] == "completed"
    assert status["current_item_id"] == "item_1"


def test_create_auto_start_without_item_ids_uses_backend_item_selection(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    class FakeOrchestrator:
        def run_items(self, request):
            seen["mode"] = request.mode
            seen["item_ids"] = list(request.item_ids)
            store = AtlasRunStore(tmp_path)
            return store.patch_state(request.run_id, {"status": "completed", "phase": "final_summary"})

    monkeypatch.setattr(atlas_runs_api, "_build_run_orchestrator", lambda request, workspace_id: FakeOrchestrator())

    created = client.post("/api/atlas/runs", json={"pool_id": "pool_sc10", "mode": "fresh", "auto_start": True})

    assert created.status_code == 200
    assert created.json()["execution_started"] is True
    assert seen == {"mode": "fresh", "item_ids": []}


def test_run_orchestrator_uses_plan_item_patch_source_with_server_control_metadata() -> None:
    assert 'requested_by="atlas_run_orchestrator"' in SOURCE
    assert 'source_type="plan_item"' in SOURCE
    assert '"server_controlled_run": True' in SOURCE
    assert 'source_type="server_controlled_run"' not in SOURCE
