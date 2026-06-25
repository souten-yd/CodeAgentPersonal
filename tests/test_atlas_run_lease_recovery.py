from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _iso(delta_seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def test_create_auto_start_acquires_durable_lease(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    class FakeOrchestrator:
        def run_items(self, request):
            store = AtlasRunStore(tmp_path)
            active = store.load_state(request.run_id)
            seen["lease_owner"] = active.lease_owner
            seen["worker_heartbeat_at"] = active.worker_heartbeat_at
            seen["request_lease_owner"] = request.metadata.get("lease_owner")
            return store.patch_state(request.run_id, {"status": "completed", "phase": "final_summary"})

    monkeypatch.setattr(atlas_runs_api, "_build_run_orchestrator", lambda request, workspace_id: FakeOrchestrator())

    created = client.post("/api/atlas/runs", json={"pool_id": "pool_cs11", "run_id": "run_cs11", "auto_start": True})

    assert created.status_code == 200
    state = created.json()["state"]
    assert state["lease_owner"].startswith("atlas_run_worker:run_cs11:")
    assert state["lease_expires_at"]
    assert state["resume_after_restart_supported"] is True
    assert seen["lease_owner"] == state["lease_owner"]
    assert seen["request_lease_owner"] == state["lease_owner"]
    assert seen["worker_heartbeat_at"]


def test_start_rejects_duplicate_active_run(client: TestClient, tmp_path: Path) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_cs11_dup"}).json()["run_id"]
    AtlasRunStore(tmp_path).patch_state(
        run_id,
        {
            "status": "running",
            "phase": "proposal",
            "lease_owner": "worker-existing",
            "lease_acquired_at": _iso(-10),
            "lease_expires_at": _iso(600),
            "worker_heartbeat_at": _iso(-1),
        },
    )

    duplicate = client.post(f"/api/atlas/runs/{run_id}/start", json={})

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error"] == "run_already_active"


def test_recover_stale_running_run_marks_blocked_not_success(client: TestClient, tmp_path: Path) -> None:
    run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_cs11_recover", "run_id": "run_stale"}).json()["run_id"]
    AtlasRunStore(tmp_path).patch_state(
        run_id,
        {
            "status": "running",
            "phase": "safe_apply",
            "lease_owner": "worker-stale",
            "lease_acquired_at": _iso(-1200),
            "lease_expires_at": _iso(-600),
            "worker_heartbeat_at": _iso(-1200),
        },
    )

    recovered = client.post("/api/atlas/runs/recover-stale", json={"stale_after_seconds": 1})

    assert recovered.status_code == 200
    body = recovered.json()
    assert body["count"] == 1
    assert body["recovered"][0]["run_id"] == run_id
    status = client.get(f"/api/atlas/runs/{run_id}/status").json()
    assert status["status"] == "blocked"
    assert status["block_reason"] == "stale_run_recovered_after_restart"
    assert status["next_actions"] == ["retry", "inspect_events"]
    assert status["terminal"] is True
    events = client.get(f"/api/atlas/runs/{run_id}/events").json()["events"]
    assert events[-1]["event_type"] == "run_recovered_stale"
