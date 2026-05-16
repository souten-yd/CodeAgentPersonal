from pathlib import Path

from fastapi.testclient import TestClient

import main


API_FILE = Path("app/api/atlas_pipeline.py")


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(client: TestClient, goal: str = "Ship Atlas API integration") -> dict:
    response = client.post("/api/atlas/plan-pools", json={"input": goal})
    assert response.status_code == 200, response.text
    return response.json()


def test_create_plan_pool_from_empty_payload_returns_fallback_pool(tmp_path) -> None:
    client = _client(tmp_path)

    body = _create_pool(client)

    assert body["status"] == "ready"
    assert body["pool_id"]
    assert body["item_count"] >= 3
    assert Path(body["checkpoint_path"]).exists()
    item_types = {item["item_type"] for item in body["plan_pool"]["items"]}
    assert {"research", "planning", "verification"}.issubset(item_types)


def test_get_plan_pool(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get(f"/api/atlas/plan-pools/{created['pool_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["pool_id"] == created["pool_id"]
    assert body["root_goal"] == "Ship Atlas API integration"


def test_get_plan_pool_markdown(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get(f"/api/atlas/plan-pools/{created['pool_id']}/markdown")

    assert response.status_code == 200
    markdown = response.json()["markdown"]
    assert "Root Goal" in markdown
    assert "Items" in markdown
    assert created["pool_id"] in markdown


def test_pipeline_dry_run_runs_fallback_pool(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"]
    assert body["pool_id"] == created["pool_id"]
    assert body["status"] in {"completed", "paused", "blocked", "failed", "completed_with_warnings"}
    assert Path(body["checkpoint_path"]).exists()
    assert body["events"]


def test_pipeline_status_requires_pool_id_or_returns_422(tmp_path) -> None:
    client = _client(tmp_path)

    response = client.get("/api/atlas/pipeline/status/run_missing")

    assert response.status_code == 422


def test_pipeline_status_returns_saved_state(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()

    response = client.get(
        f"/api/atlas/pipeline/status/{dry_run['run_id']}",
        params={"pool_id": created["pool_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == dry_run["run_id"]
    assert body["pool_id"] == created["pool_id"]
    assert body["state"]["run_id"] == dry_run["run_id"]
    assert body["events"]


def test_recovery_latest(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()

    response = client.get("/api/atlas/recovery/latest")

    assert response.status_code == 200
    summary = response.json()["recovery_summary"]
    assert summary["pool_id"] == created["pool_id"]
    assert summary["run_id"] == dry_run["run_id"]
    assert summary["status"] in {"completed", "paused", "blocked", "failed", "running", "ready"}


def test_no_task_or_agent_routes_added() -> None:
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    api_source = API_FILE.read_text(encoding="utf-8")

    assert "/api/task/plan" in paths  # existing legacy route, not added by this PR
    assert "/api/task/continue" in paths  # existing legacy route, not added by this PR
    assert "/api/agent/run" not in paths
    assert '"/api/task' not in api_source
    assert '"/api/agent' not in api_source


def test_api_does_not_expose_safe_apply(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}

    assert all("safe_apply" not in path and "safe-apply" not in path for path in paths if path.startswith("/api/atlas/"))
    response = client.post(
        "/api/atlas/pipeline/dry-run",
        json={"pool_id": created["pool_id"], "safe_apply": True},
    )
    assert response.status_code == 200
    assert response.json()["pool_id"] == created["pool_id"]


def test_api_has_no_deep_research_or_web_side_effect_tokens() -> None:
    source = API_FILE.read_text(encoding="utf-8")

    for forbidden in [
        "requests.",
        "httpx",
        "DeepResearch",
        "deep_research_job",
        "safe_apply(",
        "run_command(",
        "subprocess",
    ]:
        assert forbidden not in source
