from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


API_JS = (Path(__file__).resolve().parents[1] / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _disable_local_llm_default(monkeypatch):
    monkeypatch.setenv("ATLAS_DISABLE_LOCAL_LLM_DEFAULT", "1")


def _client(tmp_path: Path) -> TestClient:
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _create_pool(client: TestClient, workspace_id: str, goal: str) -> dict:
    response = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={"input": goal, "workspace_id": workspace_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _dry_run(client: TestClient, workspace_id: str, pool_id: str) -> dict:
    response = client.post(
        "/api/atlas/pipeline/dry-run",
        json={"workspace_id": workspace_id, "pool_id": pool_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_continuation_latest_is_workspace_scoped_and_does_not_fallback(tmp_path: Path) -> None:
    client = _client(tmp_path)
    pool_a = _create_pool(client, "project_a", "Project A plan")
    run_a = _dry_run(client, "project_a", pool_a["pool_id"])
    pool_b = _create_pool(client, "project_b", "Project B plan")

    response_a = client.get("/api/atlas/continuation/latest", params={"workspace_id": "project_a"})
    response_b = client.get("/api/atlas/continuation/latest", params={"workspace_id": "project_b"})
    response_missing = client.get("/api/atlas/continuation/latest", params={"workspace_id": "project_missing"})

    assert response_a.status_code == 200
    body_a = response_a.json()
    assert body_a["workspace_id"] == "project_a"
    assert body_a["pool_id"] == pool_a["pool_id"]
    assert body_a["run_id"] == run_a["run_id"]

    assert response_b.status_code == 200
    body_b = response_b.json()
    assert body_b["workspace_id"] == "project_b"
    assert body_b["pool_id"] == pool_b["pool_id"]
    assert body_b["run_id"] != run_a["run_id"]

    assert response_missing.status_code == 200
    body_missing = response_missing.json()
    assert body_missing["workspace_id"] == "project_missing"
    assert body_missing["pool_id"] == ""
    assert body_missing["run_id"] == ""
    assert body_missing["status"] == "no_workspace"


def test_recovery_latest_is_workspace_scoped_and_does_not_fallback_to_default(tmp_path: Path) -> None:
    client = _client(tmp_path)
    default_pool = _create_pool(client, "default", "Default workspace plan")
    pool_a = _create_pool(client, "project_a", "Project A recovery plan")
    run_a = _dry_run(client, "project_a", pool_a["pool_id"])

    response_default = client.get("/api/atlas/recovery/latest")
    response_a = client.get("/api/atlas/recovery/latest", params={"workspace_id": "project_a"})
    response_missing = client.get("/api/atlas/recovery/latest", params={"workspace_id": "project_missing"})

    assert response_default.status_code == 200
    default_summary = response_default.json()["recovery_summary"]
    assert default_summary["workspace_id"] == "default"
    assert default_summary["pool_id"] == default_pool["pool_id"]

    assert response_a.status_code == 200
    summary_a = response_a.json()["recovery_summary"]
    assert summary_a["workspace_id"] == "project_a"
    assert summary_a["pool_id"] == pool_a["pool_id"]
    assert summary_a["run_id"] == run_a["run_id"]
    assert summary_a["pool_id"] != default_pool["pool_id"]

    assert response_missing.status_code == 200
    missing_summary = response_missing.json()["recovery_summary"]
    assert missing_summary["workspace_id"] == "project_missing"
    assert missing_summary["pool_id"] == ""
    assert missing_summary["run_id"] == ""
    assert missing_summary["status"] == "no_workspace"


def test_client_restore_calls_include_workspace_id_for_recovery_and_continuation() -> None:
    for token in [
        "getContinuationLatest(workspaceId)",
        "workspace_id: workspaceId",
        "getContinuationPool(poolId, runId, workspaceId)",
        "getPlanRuntimeStatus(poolId, workspaceId)",
        "getPipelineEvents(poolId, runId, workspaceId, afterSequence)",
        "getRecoveryLatest(workspaceId)",
        "getRecoveryPool(poolId, workspaceId)",
    ]:
        assert token in API_JS
