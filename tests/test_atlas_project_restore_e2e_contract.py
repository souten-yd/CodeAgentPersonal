from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")

RUBIK_JA = (
    "ルービックキューブを解くプログラムをHTMLで作って。"
    "初期状態はランダムで、ボタンを押すと自動で順次操作されて色が全面揃うようにして。"
)


@pytest.fixture(autouse=True)
def _disable_local_llm_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DISABLE_LOCAL_LLM_DEFAULT", "1")


def _client(tmp_path: Path) -> TestClient:
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _create_project(client: TestClient, name: str) -> dict:
    response = client.post("/api/atlas/projects", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def _create_pool(client: TestClient, project: dict, goal: str) -> dict:
    response = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": goal,
            "project_name": project["name"],
            "project_path": project["project_path"],
            "workspace_id": project["workspace_id"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _dry_run(client: TestClient, project: dict, pool_id: str) -> dict:
    response = client.post(
        "/api/atlas/pipeline/dry-run",
        json={"workspace_id": project["workspace_id"], "pool_id": pool_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _persist_project_pool_meta(client: TestClient, project: dict, pool_id: str, run_id: str) -> None:
    response = client.post(
        f"/api/atlas/projects/{project['name']}/conversation",
        json={
            "role": "system",
            "text": "",
            "meta": {"active_pool_id": pool_id, "latest_autopilot_run_id": run_id},
        },
    )
    assert response.status_code == 200, response.text


def _function_body(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    paren = source.index("(", start)
    depth = 0
    close_paren = -1
    for pos in range(paren, len(source)):
        char = source[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_paren = pos
                break
    assert close_paren > -1
    brace = source.index("{", close_paren)
    depth = 0
    for pos in range(brace, len(source)):
        char = source[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:pos]
    raise AssertionError(f"{name} body not found")


def test_project_restore_e2e_contract_keeps_project_b_empty_until_it_has_own_pool(tmp_path: Path) -> None:
    client = _client(tmp_path)

    project_a = _create_project(client, "rv6-project-a")
    pool_a = _create_pool(client, project_a, "Project A plan that leaves visible run state")
    run_a = _dry_run(client, project_a, pool_a["pool_id"])
    _persist_project_pool_meta(client, project_a, pool_a["pool_id"], run_a["run_id"])

    project_b = _create_project(client, "rv6-project-b")

    conversation_b = client.get(f"/api/atlas/projects/{project_b['name']}/conversation")
    continuation_b = client.get(
        "/api/atlas/continuation/latest",
        params={"workspace_id": project_b["workspace_id"]},
    )
    recovery_b = client.get(
        "/api/atlas/recovery/latest",
        params={"workspace_id": project_b["workspace_id"]},
    )

    assert conversation_b.status_code == 200, conversation_b.text
    assert continuation_b.status_code == 200, continuation_b.text
    assert recovery_b.status_code == 200, recovery_b.text
    assert conversation_b.json()["meta"].get("active_pool_id", "") == ""
    assert continuation_b.json()["workspace_id"] == project_b["workspace_id"]
    assert continuation_b.json()["pool_id"] == ""
    assert continuation_b.json()["run_id"] == ""
    assert recovery_b.json()["recovery_summary"]["workspace_id"] == project_b["workspace_id"]
    assert recovery_b.json()["recovery_summary"]["pool_id"] == ""
    assert recovery_b.json()["recovery_summary"]["run_id"] == ""

    rubik_pool = _create_pool(client, project_b, RUBIK_JA)
    rubik_run = _dry_run(client, project_b, rubik_pool["pool_id"])
    _persist_project_pool_meta(client, project_b, rubik_pool["pool_id"], rubik_run["run_id"])

    latest_a = client.get(
        "/api/atlas/continuation/latest",
        params={"workspace_id": project_a["workspace_id"]},
    ).json()
    latest_b = client.get(
        "/api/atlas/continuation/latest",
        params={"workspace_id": project_b["workspace_id"]},
    ).json()
    recovery_a = client.get(
        "/api/atlas/recovery/latest",
        params={"workspace_id": project_a["workspace_id"]},
    ).json()["recovery_summary"]
    recovery_b_after = client.get(
        "/api/atlas/recovery/latest",
        params={"workspace_id": project_b["workspace_id"]},
    ).json()["recovery_summary"]

    assert latest_a["workspace_id"] == project_a["workspace_id"]
    assert latest_a["pool_id"] == pool_a["pool_id"]
    assert latest_a["run_id"] == run_a["run_id"]
    assert latest_b["workspace_id"] == project_b["workspace_id"]
    assert latest_b["pool_id"] == rubik_pool["pool_id"]
    assert latest_b["run_id"] == rubik_run["run_id"]
    assert latest_b["pool_id"] != pool_a["pool_id"]
    assert latest_b["run_id"] != run_a["run_id"]

    assert recovery_a["pool_id"] == pool_a["pool_id"]
    assert recovery_a["run_id"] == run_a["run_id"]
    assert recovery_b_after["workspace_id"] == project_b["workspace_id"]
    assert recovery_b_after["pool_id"] == rubik_pool["pool_id"]
    assert recovery_b_after["run_id"] == rubik_run["run_id"]

    rubik_plan_pool = rubik_pool["plan_pool"]
    assert rubik_plan_pool["project_name"] == project_b["name"]
    assert rubik_plan_pool["project_path"] == project_b["project_path"]


def test_project_restore_e2e_contract_active_project_mode_has_no_global_localstorage_restore() -> None:
    load_project_body = _function_body(PANEL_JS, "loadProject")
    activate_body = _function_body(PANEL_JS, "activate")

    assert "localStorage.getItem(STORAGE_LAST_POOL_ID_KEY" not in load_project_body
    assert "getProjectScopedHint(STORAGE_LAST_POOL_ID_KEY" not in load_project_body
    assert "if (projectName())" in activate_body
    assert "loadProject(projectName())" in activate_body
    assert "getProjectScopedHint(STORAGE_LAST_POOL_ID_KEY)" in activate_body
