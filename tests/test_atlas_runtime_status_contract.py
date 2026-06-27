import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_run_store import AtlasRunStore


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


def test_run_status_returns_backend_item_progress_counts_and_token_usage(tmp_path):
    pool_id = "pool_run_status_progress"
    pool = AtlasPlanPool(
        pool_id=pool_id,
        root_goal="Restore backend progress indicators",
        status="running",
        items=[
            _item(pool_id, "item_1", title="Update UI"),
            _item(pool_id, "item_2", title="Add tests"),
            _item(pool_id, "item_3", title="Docs"),
            _item(pool_id, "item_4", title="Blocked follow-up"),
            _item(pool_id, "item_5", title="Skipped follow-up"),
        ],
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)
    created = client.post("/api/atlas/runs", json={"pool_id": pool_id, "workspace_id": "default"}).json()
    run_id = created["run_id"]
    store = AtlasRunStore(tmp_path)
    store.patch_state(
        run_id,
        {
            "status": "running",
            "phase": "proposal",
            "current_item_id": "item_2",
            "current_item_index": 2,
            "total_items": 5,
            "completed_item_ids": ["item_1"],
            "failed_item_ids": ["item_3"],
            "blocked_item_ids": ["item_4"],
            "skipped_item_ids": ["item_5"],
        },
    )
    store.append_event(
        run_id,
        event_type="llm_token_delta",
        phase="proposal",
        status="running",
        item_id="item_2",
        metadata={"tokens_generated": 512, "max_ctx": 16384},
    )

    response = client.get(f"/api/atlas/runs/{run_id}/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed_item_ids"] == ["item_1"]
    assert body["failed_item_ids"] == ["item_3"]
    assert body["blocked_item_ids"] == ["item_4"]
    assert body["skipped_item_ids"] == ["item_5"]
    assert body["completed_count"] == 1
    assert body["failed_count"] == 1
    assert body["blocked_count"] == 1
    assert body["skipped_count"] == 1
    assert body["running_count"] == 1
    assert body["token_usage"]["generated_tokens"] == 512
    assert body["token_usage"]["tokens_generated"] == 512
    assert body["token_usage"]["max_context_tokens"] == 16384
    assert body["token_usage"]["max_ctx"] == 16384
    progress = {item["item_id"]: item for item in body["item_progress"]}
    assert progress["item_1"]["status"] == "completed"
    assert progress["item_2"]["status"] == "running"
    assert progress["item_2"]["phase"] == "proposal"
    assert progress["item_2"]["title"] == "Add tests"
    assert progress["item_3"]["status"] == "failed"
    assert progress["item_4"]["status"] == "blocked"
    assert progress["item_5"]["status"] == "skipped"


def test_run_status_token_usage_absence_does_not_break_item_progress(tmp_path):
    pool_id = "pool_run_status_no_tokens"
    _save_pool(tmp_path, AtlasPlanPool(pool_id=pool_id, root_goal="No token progress", items=[_item(pool_id)]))
    client = _client(tmp_path)
    run_id = client.post("/api/atlas/runs", json={"pool_id": pool_id, "workspace_id": "default"}).json()["run_id"]

    response = client.get(f"/api/atlas/runs/{run_id}/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_usage"]["generated_tokens"] == 0
    assert body["token_usage"]["tokens_generated"] == 0
    assert body["item_progress"] == [
        {"item_id": "item_1", "title": "Implement visible patch status", "status": "pending", "phase": ""}
    ]


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

def test_runtime_status_surfaces_plan_revision_required_block(tmp_path):
    # A plan flagged plan_revision_required hard-blocks patch generation in propose_for_item; the
    # runtime status must say so (blocked + revise plan), not look idle as "waiting / no user action".
    pool = AtlasPlanPool(
        pool_id="pool_runtime_revblock",
        root_goal="Rainbow hello world",
        status="approval_required",
        items=[
            _item(
                "pool_runtime_revblock",
                status="ready",
                metadata={"approval": {"decision": "approved"}},
            )
        ],
        metadata={
            "plan_revision_required": True,
            "critique_gate": {"gate_status": "blocked", "reason": "plan_structure_quality_gate_blocked"},
        },
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_revblock/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "patch_generation"
    assert body["status"] == "blocked"
    assert body["requires_user_action"] is True
    assert "plan_revision_required" in (body.get("block_reason") or "")
    assert "revise plan" in body["next_actions"]


def test_runtime_status_same_project_scope_restores_pool(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_project_a",
        root_goal="Project A plan",
        status="ready",
        project_name="project-a",
        project_path=str((tmp_path / "atlas" / "projects" / "project-a" / "work").resolve()),
        items=[_item("pool_runtime_project_a", status="ready", metadata={"approval": {"decision": "approved"}})],
        metadata={"workspace_id": "project-a", "runtime_scope_key": "workspace:project-a"},
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_project_a/runtime-status", params={"workspace_id": "project-a"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pool_id"] == "pool_runtime_project_a"
    assert body["status"] == "approved_not_started"
    assert body.get("restored_state_rejected") is not True


def test_runtime_status_rejects_cross_project_restore_without_foreign_fields(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_foreign",
        root_goal="FOREIGN PLAN SHOULD NOT RENDER",
        status="approval_required",
        project_name="project-a",
        project_path=str((tmp_path / "atlas" / "projects" / "project-a" / "work").resolve()),
        items=[
            _item(
                "pool_runtime_foreign",
                title="FOREIGN APPROVAL ITEM",
                status="approval_required",
                requires_user_confirmation=True,
            )
        ],
        metadata={
            "workspace_id": "project-a",
            "runtime_scope_key": "workspace:project-a",
            "safety_gate_block_reason_after_clarification": "FOREIGN_FAILURE_REASON",
        },
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_foreign/runtime-status", params={"workspace_id": "project-b"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_runtime"] is False
    assert body["runtime_restored"] is False
    assert body["restored_state_rejected"] is True
    assert body["restore_rejected_reason"] == "project_scope_mismatch"
    assert body["requires_user_action"] is False
    assert body["next_actions"] == ["wait"]
    serialized = json.dumps(body, ensure_ascii=False)
    assert "FOREIGN PLAN SHOULD NOT RENDER" not in serialized
    assert "FOREIGN APPROVAL ITEM" not in serialized
    assert "FOREIGN_FAILURE_REASON" not in serialized


def test_runtime_status_legacy_unscoped_state_fails_closed_for_project(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_legacy_unscoped",
        root_goal="Legacy unscoped plan",
        status="approval_required",
        items=[_item("pool_runtime_legacy_unscoped", status="approval_required", requires_user_confirmation=True)],
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get(
        "/api/atlas/plan-pools/pool_runtime_legacy_unscoped/runtime-status",
        params={"workspace_id": "project-b"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_runtime"] is False
    assert body["runtime_restored"] is False
    assert body["restored_state_rejected"] is True
    assert body["restore_rejected_reason"] == "missing_project_scope"
    assert body["requires_user_action"] is False
    assert body["next_actions"] == ["wait"]


def test_plan_pool_read_rejects_explicit_project_path_mismatch(tmp_path):
    project_a = (tmp_path / "atlas" / "projects" / "project-a" / "work").resolve()
    pool = AtlasPlanPool(
        pool_id="pool_project_path_foreign",
        root_goal="FOREIGN PROJECT PATH PLAN",
        status="approval_required",
        project_name="project-a",
        project_path=str(project_a),
        items=[_item("pool_project_path_foreign", title="FOREIGN PROJECT PATH ITEM")],
        metadata={
            "runtime_scope": {
                "project_path": str(project_a),
                "workspace_root": str(project_a),
            },
        },
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_project_path_foreign", params={"workspace_id": "project-b"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["restored_state_rejected"] is True
    assert body["restore_rejected_reason"] == "project_scope_mismatch"
    serialized = json.dumps(body, ensure_ascii=False)
    assert "plan_pool" not in body
    assert "FOREIGN PROJECT PATH PLAN" not in serialized
    assert "FOREIGN PROJECT PATH ITEM" not in serialized


def test_plan_pool_read_rejects_explicit_workspace_mismatch(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_workspace_foreign",
        root_goal="FOREIGN WORKSPACE PLAN",
        status="approval_required",
        project_name="project-a",
        project_path=str((tmp_path / "atlas" / "projects" / "project-a" / "work").resolve()),
        items=[_item("pool_workspace_foreign", title="FOREIGN WORKSPACE ITEM")],
        metadata={"workspace_id": "project-a", "runtime_scope_key": "workspace:project-a"},
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_workspace_foreign", params={"workspace_id": "project-b"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["restored_state_rejected"] is True
    assert body["restore_rejected_reason"] == "project_scope_mismatch"
    serialized = json.dumps(body, ensure_ascii=False)
    assert "plan_pool" not in body
    assert "FOREIGN WORKSPACE PLAN" not in serialized
    assert "FOREIGN WORKSPACE ITEM" not in serialized


def test_plan_pool_unscoped_pool_id_read_accepts_non_default_workspace_pool(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_unscoped_pool_id_lookup",
        root_goal="PIR13 restart plan",
        status="ready",
        project_name="pir13",
        project_path=str((tmp_path / "atlas" / "projects" / "pir13" / "work").resolve()),
        items=[_item("pool_unscoped_pool_id_lookup", title="PIR13 restart item", status="ready")],
        metadata={"workspace_id": "pir13", "runtime_scope_key": "workspace:pir13"},
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_unscoped_pool_id_lookup")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_pool"]["pool_id"] == "pool_unscoped_pool_id_lookup"
    assert body["plan_pool"]["metadata"]["workspace_id"] == "pir13"
    assert body.get("restored_state_rejected") is not True


def test_plan_pool_default_workspace_legacy_read_is_accepted(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_default_legacy_lookup",
        root_goal="Default legacy plan",
        status="ready",
        items=[_item("pool_default_legacy_lookup", status="ready")],
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_default_legacy_lookup", params={"workspace_id": "default"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_pool"]["pool_id"] == "pool_default_legacy_lookup"
    assert body.get("restored_state_rejected") is not True


def test_runtime_status_unscoped_request_still_rejects_foreign_scoped_pool(tmp_path):
    pool = AtlasPlanPool(
        pool_id="pool_runtime_unscoped_foreign",
        root_goal="FOREIGN RUNTIME PLAN",
        status="approval_required",
        project_name="project-a",
        project_path=str((tmp_path / "atlas" / "projects" / "project-a" / "work").resolve()),
        items=[
            _item(
                "pool_runtime_unscoped_foreign",
                title="FOREIGN RUNTIME ITEM",
                status="approval_required",
                requires_user_confirmation=True,
            )
        ],
        metadata={"workspace_id": "project-a", "runtime_scope_key": "workspace:project-a"},
    )
    _save_pool(tmp_path, pool)
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_runtime_unscoped_foreign/runtime-status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_runtime"] is False
    assert body["runtime_restored"] is False
    assert body["restored_state_rejected"] is True
    assert body["restore_rejected_reason"] == "project_scope_mismatch"
    serialized = json.dumps(body, ensure_ascii=False)
    assert "FOREIGN RUNTIME PLAN" not in serialized
    assert "FOREIGN RUNTIME ITEM" not in serialized


def test_plan_pool_status_rejects_cross_project_job_failure(tmp_path):
    jobs_dir = tmp_path / "atlas" / "plan_pool_jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "pool_job_foreign.json").write_text(
        json.dumps(
            {
                "pool_id": "pool_job_foreign",
                "workspace_id": "project-a",
                "runtime_scope_key": "workspace:project-a",
                "status": "failed",
                "error": "FOREIGN_JOB_FAILURE",
            }
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/atlas/plan-pools/pool_job_foreign/status", params={"workspace_id": "project-b"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_runtime"] is False
    assert body["runtime_restored"] is False
    assert body["restored_state_rejected"] is True
    assert body["restore_rejected_reason"] == "project_scope_mismatch"
    assert "FOREIGN_JOB_FAILURE" not in json.dumps(body, ensure_ascii=False)
