from fastapi.testclient import TestClient
from app.server import create_app
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def test_api_path_traversal_rejected():
    app = create_app()
    c = TestClient(app)
    r = c.get('/api/atlas/multi-item-autopilot/results/../x/auto_x')
    assert r.status_code in (400,404)


def test_runtime_status_exposes_backend_authorized_next_action_controls(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_dir = str(tmp_path)
    pool = AtlasPlanPool(
        pool_id="pool_next_actions",
        root_goal="Patch failed",
        status="ready",
        items=[
            AtlasPlanItem(
                pool_id="pool_next_actions",
                item_id="item_1",
                title="Implement UI",
                goal="Implement UI",
                target_files=["web/js/atlas_claude_panel.js"],
                metadata={
                    "approval": {"decision": "approved"},
                    "patch_proposal": {
                        "status": "failed",
                        "metadata": {
                            "patch_content_available": False,
                            "generation_failure_reason": "llm_returned_empty_patch_content",
                        },
                    },
                },
            )
        ],
    )
    AtlasPlanPoolStorage(tmp_path).save_pool(pool)
    c = TestClient(app)

    r = c.get("/api/atlas/plan-pools/pool_next_actions/runtime-status")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_actions"] == ["retry", "revise plan", "cancel"]
    assert body["can_retry"] is True
    assert body["can_revise_plan"] is True
    assert body["can_cancel"] is True
    assert body["can_repair"] is False
    assert body["can_rerun_pool"] is False
    assert body["can_execute"] is False
    assert body["can_continue"] is False
    assert body["controls"]["disabled_reasons"]["can_repair"]
    assert body["controls"]["disabled_reasons"]["can_rerun_pool"]
    assert body["controls"]["disabled_reasons"]["can_execute"]
