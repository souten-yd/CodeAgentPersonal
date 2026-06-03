from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_codegen_progress import read_progress, request_stop, write_progress
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client_with_pool(tmp_path: Path, pool: AtlasPlanPool, llm_json_fn=None) -> TestClient:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.state.atlas_llm_json_fn = llm_json_fn
    AtlasPlanPoolStorage(Path(tmp_path)).save_pool(pool)
    return TestClient(app)


def _pool(tmp_path: Path, *, proposed_content: str = "# x\n") -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_progress",
        root_goal="Goal",
        project_path=str(tmp_path),
        status="ready",
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="pool_progress",
                title="Item",
                goal="Do it",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["src/i1.py"],
                metadata={"action_type": "create", **({"proposed_content": proposed_content} if proposed_content else {})},
            )
        ],
    )


def test_progress_helper_roundtrip_and_stop(tmp_path: Path) -> None:
    write_progress(tmp_path, "pool_1", "acg_1", {"phase": "candidate_apply", "current_item_index": 1, "total_items": 3})
    progress = read_progress(tmp_path, "pool_1", "acg_1")
    assert progress["phase"] == "candidate_apply"
    assert progress["current_item_index"] == 1
    assert progress["heartbeat_at"]

    stopped = request_stop(tmp_path, "pool_1", "acg_1")
    assert stopped["stop_requested"] is True
    assert read_progress(tmp_path, "pool_1", "acg_1")["last_event"] == "stop_requested"


def test_start_returns_run_handle_and_status_reads_progress(tmp_path: Path) -> None:
    client = _client_with_pool(tmp_path, _pool(tmp_path))

    started = client.post("/api/atlas/autonomous-codegen/start", json={"pool_id": "pool_progress"}).json()

    assert started["status"] == "running"
    assert started["run_id"]
    assert started["orchestrator_run_id"]
    progress = read_progress(tmp_path, "pool_progress", started["orchestrator_run_id"])
    assert progress["run_id"] == started["run_id"]

    status = client.get(f"/api/atlas/autonomous-codegen/status/pool_progress/{started['orchestrator_run_id']}")
    assert status.status_code == 200
    body = status.json()
    assert body["current_phase"]
    assert "processed_count" in body["plan_summary"]
    assert "total_count" in body["plan_summary"]


def test_status_returns_progress_when_result_json_is_missing(tmp_path: Path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    client = TestClient(app)
    write_progress(tmp_path, "pool_progress", "acg_progress", {"pool_id": "pool_progress", "run_id": "run_1", "orchestrator_run_id": "acg_progress", "phase": "candidate_apply", "sub_phase": "safe_apply", "current_item_index": 1, "total_items": 2})

    status = client.get("/api/atlas/autonomous-codegen/status/pool_progress/acg_progress")

    assert status.status_code == 200
    body = status.json()
    assert body["current_phase"] == "candidate_apply"
    assert body["sub_phase"] == "safe_apply"
    assert body["plan_summary"]["processed_count"] == 1
    assert body["plan_summary"]["total_count"] == 2


def test_stop_marks_progress_stop_requested(tmp_path: Path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    client = TestClient(app)
    write_progress(tmp_path, "pool_progress", "acg_progress", {"pool_id": "pool_progress", "run_id": "run_1", "orchestrator_run_id": "acg_progress"})

    stopped = client.post("/api/atlas/autonomous-codegen/stop", json={"pool_id": "pool_progress", "run_id": "run_1"}).json()

    assert stopped["status"] == "stopped"
    assert read_progress(tmp_path, "pool_progress", "acg_progress")["stop_requested"] is True


def test_model_call_timeout_updates_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_LLM_CALL_TIMEOUT_SECONDS", "1")

    def slow_llm(_prompt: str, _user_input: str):
        time.sleep(1.5)
        return {"title": "late"}

    client = _client_with_pool(tmp_path, _pool(tmp_path, proposed_content=""), llm_json_fn=slow_llm)
    started = client.post("/api/atlas/autonomous-codegen/start", json={"pool_id": "pool_progress"}).json()

    progress = read_progress(tmp_path, "pool_progress", started["orchestrator_run_id"])
    assert progress["last_event"] in {"model_call_timeout", "autonomous_codegen_completed"}
    assert progress["waiting_on_model_seconds"] >= 1
