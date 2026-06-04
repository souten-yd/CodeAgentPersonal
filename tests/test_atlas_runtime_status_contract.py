import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _save_pool(tmp_path: Path, pool: AtlasPlanPool) -> None:
    AtlasPlanPoolStorage(tmp_path).save_pool(pool)


def _item(pool_id: str, item_id: str = "item_1", **kwargs) -> AtlasPlanItem:
    return AtlasPlanItem(
        pool_id=pool_id,
        item_id=item_id,
        title=kwargs.pop("title", "Implement visible patch status"),
        goal=kwargs.pop("goal", "Show runtime status"),
        target_files=kwargs.pop("target_files", ["web/js/atlas_claude_panel.js"]),
        **kwargs,
    )


def test_runtime_status_approved_pool_is_clear_approved_not_started(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_approved",
        root_goal="Ship status panel",
        status="ready",
        items=[
            _item(
                "pool_runtime_approved",
                status="ready",
                metadata={"approval": {"decision": "approved"}},
            )
        ],
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_approved/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "patch_generation"
    assert body["status"] == "approved_not_started"
    assert body["message"] == "Patch generation has not started"
    assert body["items_total"] == 1
    assert body["next_actions"]


def test_runtime_status_item_approved_even_if_pool_status_is_stale_approval_required(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_stale_approval",
        root_goal="Approved item but stale pool status",
        status="approval_required",
        items=[
            _item(
                "pool_runtime_stale_approval",
                status="ready",
                requires_user_confirmation=True,
                metadata={"approval": {"decision": "approved"}},
            )
        ],
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_stale_approval/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "patch_generation"
    assert body["status"] == "approved_not_started"
    assert body["message"] == "Patch generation has not started"
    assert body["requires_user_action"] is False


def test_runtime_status_safety_block_returns_visible_reason(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_blocked",
        root_goal="Blocked plan",
        status="blocked_safety_review",
        items=[_item("pool_runtime_blocked")],
        metadata={"safety_gate_block_reason_after_clarification": "target_files_too_many"},
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_blocked/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "blocked_safety_review"
    assert body["status"] == "blocked"
    assert body["block_reason"] == "target_files_too_many"
    assert body["requires_user_action"] is True
    assert "override safety block" in body["next_actions"]


def test_runtime_status_patch_generation_failed_before_first_patch(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_patch_failed",
        root_goal="Patch failed",
        status="ready",
        items=[
            _item(
                "pool_runtime_patch_failed",
                metadata={
                    "approval": {"decision": "approved"},
                    "patch_proposal": {
                        "status": "proposed",
                        "warnings": ["llm_no_patch_content_generated"],
                        "metadata": {
                            "patch_content_available": False,
                            "generation_failure_reason": "llm_returned_empty_patch_content",
                        },
                    },
                },
            )
        ],
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_patch_failed/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "failed"
    assert body["status"] == "failed"
    assert body["message"] == "Patch generation failed before first patch"
    assert "llm_returned_empty_patch_content" in body["error"]
    assert body["requires_user_action"] is True


def test_runtime_status_uses_latest_autopilot_result_when_available(tmp_path):
    pool_id = "pool_runtime_autopilot"
    pool = AtlasPlanPool(
        pool_id=pool_id,
        root_goal="Autopilot status",
        status="running",
        items=[_item(pool_id, metadata={"approval": {"decision": "approved"}})],
    )
    _save_pool(tmp_path, pool)
    out_dir = tmp_path / "atlas" / "multi_item_autopilot" / pool_id
    out_dir.mkdir(parents=True)
    (out_dir / "auto_runtime.json").write_text(
        json.dumps(
            {
                "pool_id": pool_id,
                "run_id": "run_runtime",
                "autopilot_run_id": "auto_runtime",
                "status": "completed",
                "processed_count": 1,
                "completed_count": 1,
                "failed_count": 0,
                "blocked_count": 0,
            }
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get(f"/api/atlas/plan-pools/{pool_id}/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "completed"
    assert body["status"] == "completed"
    assert body["run_id"] == "run_runtime"
    assert body["autopilot_run_id"] == "auto_runtime"
    assert body["items_completed"] == 1
