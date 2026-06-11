from fastapi.testclient import TestClient
from app.server import create_app


def test_planpool_post_attaches_handoff_metadata_and_advisory_flags(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    r = c.post('/api/atlas/plan-pools?sync=1', json={"workspace_id":"default","input":"x","project_path":".","enable_repo_context":True,"mode":"local"})
    assert r.status_code == 200
    data = r.json()
    pool = data["plan_pool"]
    handoff = pool["metadata"]["verification_recommendation_handoff"]
    assert handoff
    for k in ["approval_summary","impacted_files","related_tests","recommended_commands","manual_verification_steps"]:
        assert k in handoff
    assert handoff["advisory_only"] is True
    assert handoff["executed"] is False
    assert handoff["manual_approval_only"] is True
    assert handoff["auto_verification_triggered"] is False
    assert handoff["auto_test_execution_triggered"] is False
    assert data["plan_pool"]["metadata"]["verification_recommendation_handoff"]
    if pool.get("items"):
        item_handoff = pool["items"][0]["metadata"]["verification_recommendation_handoff"]
        assert item_handoff["manual_approval_only"] is True


def test_enable_repo_context_false_does_not_add_active_handoff(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    r = c.post('/api/atlas/plan-pools?sync=1', json={"workspace_id":"default","input":"x","project_path":".","enable_repo_context":False,"mode":"local"})
    assert r.status_code == 200
    assert "verification_recommendation_handoff" not in r.json()["plan_pool"]["metadata"]
