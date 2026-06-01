from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path: Path, pool: AtlasPlanPool) -> TestClient:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    AtlasPlanPoolStorage(Path(tmp_path)).save_pool(pool)
    return TestClient(app)


def _pool(*, status="approval_required", item_status="approval_required", metadata=None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_x",
        root_goal="Goal",
        status=status,
        items=[
            AtlasPlanItem(
                item_id="i1", pool_id="pool_x", title="Item", goal="Do",
                item_type="implementation", status=item_status, risk_level="medium",
                target_files=["src/i1.py"], metadata={"action_type": "create"},
            )
        ],
        metadata=metadata or {},
    )


def test_cancel_marks_pool_and_items_cancelled(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post("/api/atlas/plan-pools/pool_x/cancel", json={"reason": "user aborted"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_item_ids"] == ["i1"]
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.status == "cancelled"
    assert reloaded.get_item("i1").status == "cancelled"


def test_cancel_missing_pool_returns_404(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post("/api/atlas/plan-pools/nope/cancel", json={})
    assert r.status_code == 404


def test_approvals_decide_cancelled_marks_item_cancelled(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post("/api/atlas/approvals/decide", json={"pool_id": "pool_x", "item_id": "i1", "decision": "cancelled"})
    assert r.status_code == 200, r.text
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.get_item("i1").status == "cancelled"
    assert reloaded.get_item("i1").metadata["approval"]["decision"] == "cancelled"


def test_clarify_records_decision_and_clears_flag(tmp_path: Path):
    options = [{"option_id": "revise_0", "label": "Security", "description": "fix auth"}]
    pool = _pool(metadata={
        "clarification_required": True,
        "critique_clarification_options": {"options": options},
    })
    client = _client(tmp_path, pool)
    r = client.post("/api/atlas/plan-pools/pool_x/clarify", json={"option_id": "revise_0", "note": "go"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["clarification_decision"]["option_id"] == "revise_0"
    assert body["clarification_decision"]["chosen"]["label"] == "Security"
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert "clarification_required" not in (reloaded.metadata or {})
    assert reloaded.metadata["clarification_decision"]["note"] == "go"
