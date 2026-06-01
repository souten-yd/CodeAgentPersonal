from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client_with_pool(tmp_path: Path, pool: AtlasPlanPool | None = None) -> TestClient:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    if pool is not None:
        AtlasPlanPoolStorage(Path(tmp_path)).save_pool(pool)
    return TestClient(app)


def test_run_returns_404_for_missing_pool(tmp_path: Path) -> None:
    client = _client_with_pool(tmp_path)
    r = client.post("/api/atlas/autonomous-codegen/run", json={"pool_id": "does_not_exist"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "pool_not_found"


def test_run_returns_integrated_result_for_existing_pool(tmp_path: Path) -> None:
    pool = AtlasPlanPool(
        pool_id="pool_api_1",
        root_goal="Goal",
        project_path=str(tmp_path),
        status="ready",
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="pool_api_1",
                title="Item",
                goal="Do it",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["src/i1.py"],
                metadata={"action_type": "create"},
            )
        ],
    )
    client = _client_with_pool(tmp_path, pool)

    r = client.post("/api/atlas/autonomous-codegen/run", json={"pool_id": "pool_api_1"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pool_id"] == "pool_api_1"
    assert body["orchestrator_run_id"]
    assert body["phase"] in {"final_summary", "candidate_apply", "candidate_generation"}
    assert "autopilot_result" in body
    # The pool is tagged full_autopilot for downstream single-item pipeline consistency.
    assert AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_api_1").automation_level == "full_autopilot"


def test_run_stops_safely_when_project_path_missing(tmp_path: Path) -> None:
    pool = AtlasPlanPool(
        pool_id="pool_api_missing_path",
        root_goal="Goal",
        status="ready",
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="pool_api_missing_path",
                title="Item",
                goal="Do it",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["src/i1.py"],
                metadata={"action_type": "create"},
            )
        ],
    )
    client = _client_with_pool(tmp_path, pool)

    r = client.post("/api/atlas/autonomous-codegen/run", json={"pool_id": "pool_api_missing_path"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "stopped"
    assert body["stop_reason"] == "missing_project_path"


def test_result_status_read_and_stop_endpoints(tmp_path: Path) -> None:
    pool = AtlasPlanPool(
        pool_id="pool_api_read",
        root_goal="Goal",
        project_path=str(tmp_path),
        status="ready",
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="pool_api_read",
                title="Item",
                goal="Do it",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["src/i1.py"],
                metadata={"action_type": "create", "proposed_content": "# x\n"},
            )
        ],
    )
    client = _client_with_pool(tmp_path, pool)
    run = client.post("/api/atlas/autonomous-codegen/start", json={"pool_id": "pool_api_read"}).json()
    rid = run["orchestrator_run_id"]

    read = client.get(f"/api/atlas/autonomous-codegen/results/pool_api_read/{rid}")
    status = client.get(f"/api/atlas/autonomous-codegen/status/pool_api_read/{rid}")
    latest = client.get("/api/atlas/autonomous-codegen/latest/pool_api_read")
    stopped = client.post("/api/atlas/autonomous-codegen/stop", json={"pool_id": "pool_api_read", "run_id": run["run_id"]})

    assert read.status_code == 200
    assert status.status_code == 200
    assert status.json()["current_phase"]
    assert status.json()["raw_json_included"] is False
    assert "summary" not in status.json()
    assert "active_profile" in status.json()
    assert "decision_targets" in status.json()
    assert "evidence_summary" in status.json()
    assert status.json()["controls"]["execute_apply_visible"] is False
    assert latest.status_code == 200
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"


def test_status_surfaces_decision_targets_without_raw_summary(tmp_path: Path) -> None:
    pool = AtlasPlanPool(
        pool_id="pool_api_decisions",
        root_goal="Goal",
        project_path=str(tmp_path),
        status="needs_scope_confirmation",
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="pool_api_decisions",
                title="Item",
                goal="Do it",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["src/i1.py"],
                metadata={"action_type": "create", "proposed_content": "# x\n"},
            )
        ],
    )
    client = _client_with_pool(tmp_path, pool)
    run = client.post("/api/atlas/autonomous-codegen/start", json={"pool_id": "pool_api_decisions"}).json()

    status = client.get(f"/api/atlas/autonomous-codegen/status/pool_api_decisions/{run['orchestrator_run_id']}")

    assert status.status_code == 200
    body = status.json()
    assert body["automation_state"] == "blocked"
    assert body["decision_targets"]["clarification"]["visible"] is True
    assert body["controls"]["can_answer_clarification"] is True
    assert body["raw_json_included"] is False
