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
    # No project_path -> the multi-item engine marks items ineligible (project_path_missing) and the
    # run is side-effect-free, while still exercising the full orchestrator endpoint wiring.
    pool = AtlasPlanPool(
        pool_id="pool_api_1",
        root_goal="Goal",
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
    assert body["phase"] in {"completed", "apply", "patch_generation"}
    assert "autopilot_result" in body
    # The pool is tagged full_autopilot for downstream single-item pipeline consistency.
    assert AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_api_1").automation_level == "full_autopilot"
