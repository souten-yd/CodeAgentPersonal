from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from tests.test_atlas_safe_apply_execution_api import _clear_safe_apply_state


def _client(tmp_path: Path, repo: Path) -> TestClient:
    _clear_safe_apply_state()
    main.app.state.atlas_ca_data_dir = str(tmp_path / "atlas_data")
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    main.app.state.atlas_llm_json_fn = _greenfield_html_llm
    return TestClient(main.app)


def _greenfield_html_llm(_system_prompt: str, _user_prompt: str) -> dict:
    return {
        "summary": "Create a single-file HTML status page.",
        "proposed_fix": "Write index.html with a visible ready indicator.",
        "target_files": ["index.html"],
        "risk_level": "low",
        "proposed_content": (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head><meta charset=\"utf-8\"><title>Atlas Greenfield</title></head>\n"
            "<body><main><h1>Atlas Greenfield Ready</h1><p id=\"status\">ready</p></main></body>\n"
            "</html>\n"
        ),
        "suggested_changes": [{"path": "index.html", "action": "create"}],
        "verification_plan": ["Assert index.html contains the ready status."],
        "rollback_plan": ["Delete index.html."],
    }


def test_pir13_normal_entrypoint_single_html_reaches_real_safe_apply(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    repo.mkdir()
    client = _client(tmp_path, repo)

    plan_payload = {
        "root_goal": "Create a Greenfield single HTML app.",
        "requirements": [{"id": "REQ-HTML", "text": "Render a ready status in index.html."}],
        "implementation_steps": [
            {
                "step_id": "html",
                "title": "Create index.html",
                "description": "Create a single HTML page with a visible ready status.",
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["index.html"],
                "acceptance_criteria": ["index.html contains Atlas Greenfield Ready and ready."],
            }
        ],
    }

    created = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Create a Greenfield single HTML app.",
            "project_path": str(repo),
            "project_name": "pir13-greenfield",
            "workspace_id": "pir13",
            "plan_payload": plan_payload,
        },
    ).json()
    assert created["status"] == "ready"
    pool_id = created["pool_id"]
    source_item_id = created["plan_pool"]["items"][0]["item_id"]

    proposed = client.post(
        "/api/atlas/patch-proposals/generate",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_patchgen",
            "source_type": "plan_item",
        },
    ).json()
    assert proposed["status"] == "proposed", proposed
    assert proposed["metadata"]["patch_generation"]["outcome"] == "success"

    approved_proposal = client.post(
        "/api/atlas/patch-proposals/decide",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "decision": "approved",
            "reason": "PIR-13 normal entrypoint scenario approval.",
        },
    ).json()
    assert approved_proposal["status"] == "approved", approved_proposal

    draft = client.post(
        "/api/atlas/patch-proposals/planitem-draft",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "run_id": "pir13_draft",
        },
    ).json()
    assert draft["status"] == "created", draft
    draft_item_id = draft["draft_item"]["draft_item_id"]
    assert draft["draft_item"]["metadata"]["patch_generation"]["outcome"] == "success"
    assert draft["draft_item"]["metadata"]["action_type"] == "create"

    approved_item = client.post(
        "/api/atlas/approvals/decide",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "decision": "approved",
            "reason": "Approve only this drafted PlanItem for Safe Apply.",
        },
    ).json()
    assert approved_item["decision"] == "approved", approved_item
    approved_draft = next(
        item for item in approved_item["plan_pool"]["items"] if item["item_id"] == draft_item_id
    )
    assert approved_draft["metadata"]["approval"]["decision"] == "approved"

    applied = client.post(
        "/api/atlas/safe-apply/execute",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_safe_apply",
        },
    ).json()
    assert applied["status"] == "applied", applied
    html = repo / "index.html"
    assert html.exists()
    assert "Atlas Greenfield Ready" in html.read_text(encoding="utf-8")
    assert applied["metadata"]["workspace_root"] == str(repo.resolve())
    assert applied["metadata"]["executor_result"]["actual_file_changed"] is True
    assert applied["metadata"]["executor_result"]["changed_files"] == ["index.html"]
    assert Path(applied["metadata"]["change_snapshot"]["manifest_path"]).exists()
