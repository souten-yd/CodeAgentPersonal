from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.test_command_runner import TestCommandRunner
from app.server import create_app
from tests.test_atlas_safe_apply_execution_api import _clear_safe_apply_state


def _client(tmp_path: Path, repo: Path, llm_json_fn=None) -> TestClient:
    _clear_safe_apply_state()
    main.app.state.atlas_ca_data_dir = str(tmp_path / "atlas_data")
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    main.app.state.atlas_llm_json_fn = llm_json_fn or _greenfield_html_llm
    main.app.state.atlas_test_command_runner = lambda: TestCommandRunner(
        allowed_commands=["python -m pytest -q"]
    )
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


def _broken_animation_html_llm(_system_prompt: str, user_prompt: str) -> dict:
    repairing = "fix_verification_failure" in user_prompt
    content = _fixed_animation_html() if repairing else _static_animation_failure_html()
    return {
        "summary": "Create a single-file HTML color animation.",
        "proposed_fix": "Write index.html with visible color animation evidence.",
        "target_files": ["index.html"],
        "risk_level": "low",
        "proposed_content": content,
        "suggested_changes": [{"path": "index.html", "action": "create" if not repairing else "update"}],
        "verification_plan": ["Verify index.html contains color animation signals."],
        "rollback_plan": ["Restore the previous index.html snapshot."],
    }


def _static_animation_failure_html() -> str:
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head><meta charset=\"utf-8\"><title>Atlas Color Animation</title></head>\n"
        "<body><main><h1>Animate colors</h1><p>The page is static.</p></main></body>\n"
        "</html>\n"
    )


def _fixed_animation_html() -> str:
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <title>Atlas Color Animation</title>\n"
        "  <style>\n"
        "    @keyframes atlasHue {\n"
        "      0% { background-color: hsl(0, 90%, 55%); color: rgb(255, 255, 255); }\n"
        "      50% { background-color: hsl(180, 90%, 45%); color: rgb(20, 20, 20); }\n"
        "      100% { background-color: hsl(360, 90%, 55%); color: rgb(255, 255, 255); }\n"
        "    }\n"
        "    body { margin: 0; font-family: system-ui, sans-serif; }\n"
        "    main {\n"
        "      min-height: 100vh;\n"
        "      display: grid;\n"
        "      place-items: center;\n"
        "      animation: atlasHue 1.4s linear infinite;\n"
        "    }\n"
        "  </style>\n"
        "</head>\n"
        "<body><main data-atlas-animation-running=\"true\" data-atlas-color-phase=\"active\">"
        "<h1>Animate colors with a visible continuous color animation</h1></main></body>\n"
        "</html>\n"
    )


def _python_cli_repair_llm(_system_prompt: str, user_prompt: str) -> dict:
    repairing = "fix_verification_failure" in user_prompt
    return {
        "summary": "Create a Python CLI module with an answer function.",
        "proposed_fix": "Write cli_app.py so the CLI and tests return atlas-ok.",
        "target_files": ["cli_app.py"],
        "risk_level": "low",
        "proposed_content": _fixed_python_cli() if repairing else _broken_python_cli(),
        "suggested_changes": [{"path": "cli_app.py", "action": "create" if not repairing else "update"}],
        "verification_plan": ["Provide answer function that returns atlas-ok for the Python CLI."],
        "rollback_plan": ["Restore the previous cli_app.py snapshot."],
    }


def _broken_python_cli() -> str:
    return (
        "def answer() -> str:\n"
        "    \"\"\"Provide answer function returns atlas ok for the Python CLI module.\"\"\"\n"
        "    return \"wrong\"\n"
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
        "    print(answer())\n"
    )


def _fixed_python_cli() -> str:
    return (
        "def answer() -> str:\n"
        "    \"\"\"Provide answer function returns atlas ok for the Python CLI module.\"\"\"\n"
        "    return \"atlas-ok\"\n"
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
        "    print(answer())\n"
    )


def _fastapi_api_llm(_system_prompt: str, _user_prompt: str) -> dict:
    return {
        "summary": "Create a FastAPI API with a health endpoint.",
        "proposed_fix": "Write app/main.py with a FastAPI app and GET /health route.",
        "target_files": ["app/main.py"],
        "risk_level": "low",
        "proposed_content": _fastapi_api_main(),
        "suggested_changes": [{"path": "app/main.py", "action": "create"}],
        "verification_plan": ["Expose FastAPI app with GET /health returning status ok."],
        "rollback_plan": ["Delete app/main.py."],
    }


def _fastapi_api_main() -> str:
    return (
        "from fastapi import FastAPI\n"
        "\n"
        "app = FastAPI(title=\"Atlas FastAPI Scenario\")\n"
        "\n"
        "\n"
        "@app.get(\"/health\")\n"
        "def health() -> dict[str, str]:\n"
        "    \"\"\"Expose FastAPI app GET health returning status ok.\"\"\"\n"
        "    return {\"status\": \"ok\"}\n"
    )


def _fastapi_sqlite_llm(_system_prompt: str, _user_prompt: str) -> dict:
    return {
        "summary": "Create a FastAPI API with SQLite persistence.",
        "proposed_fix": "Write app/main.py with SQLite-backed item create/read endpoints.",
        "target_files": ["app/main.py"],
        "risk_level": "low",
        "proposed_content": _fastapi_sqlite_main(),
        "suggested_changes": [{"path": "app/main.py", "action": "create"}],
        "verification_plan": [
            "Persist items in SQLite and return them after FastAPI app reload."
        ],
        "rollback_plan": ["Delete app/main.py and its SQLite database file."],
    }


def _fastapi_sqlite_main() -> str:
    return (
        "from pathlib import Path\n"
        "import sqlite3\n"
        "\n"
        "from fastapi import FastAPI, HTTPException\n"
        "from pydantic import BaseModel\n"
        "\n"
        "DB_PATH = Path(__file__).with_name(\"atlas_items.sqlite3\")\n"
        "app = FastAPI(title=\"Atlas SQLite Scenario\")\n"
        "\n"
        "\n"
        "class ItemIn(BaseModel):\n"
        "    name: str\n"
        "\n"
        "\n"
        "def _connect() -> sqlite3.Connection:\n"
        "    connection = sqlite3.connect(DB_PATH)\n"
        "    connection.row_factory = sqlite3.Row\n"
        "    return connection\n"
        "\n"
        "\n"
        "def _init_db() -> None:\n"
        "    with _connect() as connection:\n"
        "        connection.execute(\n"
        "            \"CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)\"\n"
        "        )\n"
        "\n"
        "\n"
        "_init_db()\n"
        "\n"
        "\n"
        "@app.post(\"/items\")\n"
        "def create_item(item: ItemIn) -> dict[str, object]:\n"
        "    \"\"\"Persist items in SQLite and return the created row.\"\"\"\n"
        "    with _connect() as connection:\n"
        "        cursor = connection.execute(\"INSERT INTO items (name) VALUES (?)\", (item.name,))\n"
        "        item_id = int(cursor.lastrowid)\n"
        "    return {\"id\": item_id, \"name\": item.name}\n"
        "\n"
        "\n"
        "@app.get(\"/items/{item_id}\")\n"
        "def read_item(item_id: int) -> dict[str, object]:\n"
        "    \"\"\"Return persisted items after FastAPI app reload.\"\"\"\n"
        "    with _connect() as connection:\n"
        "        row = connection.execute(\"SELECT id, name FROM items WHERE id = ?\", (item_id,)).fetchone()\n"
        "    if row is None:\n"
        "        raise HTTPException(status_code=404, detail=\"item_not_found\")\n"
        "    return {\"id\": int(row[\"id\"]), \"name\": str(row[\"name\"])}\n"
    )


def _frontend_backend_llm(_system_prompt: str, _user_prompt: str) -> dict:
    return {
        "summary": "Create a FastAPI backend with a browser frontend.",
        "proposed_fix": "Write app/main.py serving HTML that fetches /api/message.",
        "target_files": ["app/main.py"],
        "risk_level": "low",
        "proposed_content": _frontend_backend_main(),
        "suggested_changes": [{"path": "app/main.py", "action": "create"}],
        "verification_plan": [
            "Browser frontend fetches backend API and displays atlas browser api ok."
        ],
        "rollback_plan": ["Delete app/main.py."],
    }


def _frontend_backend_main() -> str:
    return (
        "from fastapi import FastAPI\n"
        "from fastapi.responses import HTMLResponse\n"
        "\n"
        "app = FastAPI(title=\"Atlas Frontend Backend Scenario\")\n"
        "\n"
        "\n"
        "@app.get(\"/api/message\")\n"
        "def api_message() -> dict[str, str]:\n"
        "    \"\"\"Backend API returns atlas browser api ok for the frontend.\"\"\"\n"
        "    return {\"message\": \"atlas browser api ok\"}\n"
        "\n"
        "\n"
        "@app.get(\"/\", response_class=HTMLResponse)\n"
        "def index() -> str:\n"
        "    \"\"\"Browser frontend fetches backend API and displays atlas browser api ok.\"\"\"\n"
        "    return \"\"\"<!doctype html>\n"
        "<html lang=\\\"en\\\">\n"
        "<head><meta charset=\\\"utf-8\\\"><title>Atlas Browser API</title></head>\n"
        "<body>\n"
        "  <main>\n"
        "    <h1>Atlas Browser API</h1>\n"
        "    <button id=\\\"load\\\" type=\\\"button\\\">Load message</button>\n"
        "    <p id=\\\"message\\\" aria-live=\\\"polite\\\">waiting</p>\n"
        "  </main>\n"
        "  <script>\n"
        "    document.getElementById('load').addEventListener('click', async () => {\n"
        "      const response = await fetch('/api/message');\n"
        "      const payload = await response.json();\n"
        "      document.getElementById('message').textContent = payload.message;\n"
        "    });\n"
        "  </script>\n"
        "</body>\n"
        "</html>\"\"\"\n"
    )


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

    verified = client.post(
        "/api/atlas/automation/verify-one",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_visual_verify",
        },
    ).json()
    assert verified["status"] == "passed", verified
    assert verified["metadata"]["visual_contract"]["status"] == "passed"
    assert verified["metadata"]["browser_smoke"]["status"] in {
        "browser_smoke_passed",
        "browser_smoke_skipped",
    }
    assert verified["metadata"]["verify_level"] in {"static_checked", "runtime_smoke_checked"}
    verified_draft = next(
        item for item in verified["plan_pool"]["items"] if item["item_id"] == draft_item_id
    )
    assert verified_draft["metadata"]["auto_verification"]["status"] == "passed"
    events_path = (
        Path(main.app.state.atlas_ca_data_dir)
        / "atlas"
        / "workspaces"
        / "pir13"
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_visual_verify"
        / "events.ndjson"
    )
    assert '"event_type": "auto_verification_passed"' in events_path.read_text(encoding="utf-8")

    restarted_app = create_app()
    restarted_app.state.atlas_ca_data_dir = main.app.state.atlas_ca_data_dir
    restarted_client = TestClient(restarted_app)
    reloaded = restarted_client.get(f"/api/atlas/plan-pools/{pool_id}").json()["plan_pool"]
    reloaded_draft = next(item for item in reloaded["items"] if item["item_id"] == draft_item_id)
    assert reloaded_draft["metadata"]["safe_apply"]["status"] == "applied"
    assert reloaded_draft["metadata"]["auto_verification"]["status"] == "passed"
    assert reloaded_draft["metadata"]["auto_verification"]["browser_smoke_status"] in {
        "browser_smoke_passed",
        "browser_smoke_skipped",
    }

    recovery = restarted_client.get(
        f"/api/atlas/recovery/pools/{pool_id}", params={"workspace_id": "pir13"}
    ).json()
    assert recovery["recovery_summary"]["pool_id"] == pool_id
    assert recovery["recovery_summary"]["total_items"] == 2
    assert recovery["recovery_summary"]["completed_count"] >= 1

    continuation = restarted_client.get(
        f"/api/atlas/continuation/pools/{pool_id}", params={"workspace_id": "pir13"}
    ).json()
    assert continuation["pool_id"] == pool_id
    assert draft_item_id in continuation["continuation_prompt"]


def test_pir13_normal_entrypoint_fault_repair_recovers_and_resumes(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    repo.mkdir()
    client = _client(tmp_path, repo, llm_json_fn=_broken_animation_html_llm)

    plan_payload = {
        "root_goal": "Create a Greenfield HTML page that animates colors.",
        "requirements": [
            {
                "id": "REQ-COLOR",
                "text": "Animate colors with a visible continuous color animation in index.html.",
            }
        ],
        "implementation_steps": [
            {
                "step_id": "html",
                "title": "Create animated index.html",
                "description": "Create a single HTML page with visible continuous color animation.",
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["index.html"],
                "acceptance_criteria": [
                    "index.html includes CSS animation and visible color mutation signals."
                ],
            }
        ],
    }

    created = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Create a Greenfield HTML page that animates colors.",
            "project_path": str(repo),
            "project_name": "pir13-greenfield-repair",
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
            "run_id": "pir13_fault_patchgen",
            "source_type": "plan_item",
        },
    ).json()
    assert proposed["status"] == "proposed", proposed
    assert "The page is static" in proposed["proposal"]["metadata"]["proposed_content"]

    approved_proposal = client.post(
        "/api/atlas/patch-proposals/decide",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "decision": "approved",
            "reason": "PIR-13 fault-repair scenario approval.",
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
            "run_id": "pir13_fault_draft",
        },
    ).json()
    assert draft["status"] == "created", draft
    draft_item_id = draft["draft_item"]["draft_item_id"]

    approved_item = client.post(
        "/api/atlas/approvals/decide",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "decision": "approved",
            "reason": "Approve only this drafted PlanItem for bounded repair proof.",
        },
    ).json()
    assert approved_item["decision"] == "approved", approved_item

    repaired = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_fault_repair",
        },
    ).json()
    assert repaired["status"] == "applied_and_verified", repaired
    verification = repaired["auto_verification_result"]
    assert verification["status"] == "passed", verification
    assert verification["metadata"]["recovered_by_self_correction"] is True
    self_correction = verification["metadata"]["self_correction_result"]
    assert self_correction["status"] == "recovered"
    assert self_correction["attempts"] == 1
    assert self_correction["final_verification_status"] == "passed"
    assert repaired["failure_stop_suggestion"] == {}

    html = (repo / "index.html").read_text(encoding="utf-8")
    assert "The page is static" not in html
    assert "animation: atlasHue" in html
    assert "data-atlas-color-phase" in html

    events_path = (
        Path(main.app.state.atlas_ca_data_dir)
        / "atlas"
        / "workspaces"
        / "pir13"
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_fault_repair"
        / "events.ndjson"
    )
    events_text = events_path.read_text(encoding="utf-8")
    assert '"event_type": "auto_verification_failed"' in events_text
    assert '"event_type": "self_correction_attempt"' in events_text
    assert '"event_type": "self_correction_recovered"' in events_text
    assert '"event_type": "auto_verification_passed"' in events_text

    restarted_app = create_app()
    restarted_app.state.atlas_ca_data_dir = main.app.state.atlas_ca_data_dir
    restarted_client = TestClient(restarted_app)
    reloaded = restarted_client.get(f"/api/atlas/plan-pools/{pool_id}").json()["plan_pool"]
    reloaded_draft = next(item for item in reloaded["items"] if item["item_id"] == draft_item_id)
    assert reloaded_draft["metadata"]["auto_verification"]["status"] == "passed"
    assert reloaded_draft["metadata"]["verification"]["status"] == "failed"

    recovery = restarted_client.get(
        f"/api/atlas/recovery/pools/{pool_id}", params={"workspace_id": "pir13"}
    ).json()
    assert recovery["recovery_summary"]["pool_id"] == pool_id
    assert recovery["recovery_summary"]["completed_count"] >= 1

    continuation = restarted_client.get(
        f"/api/atlas/continuation/pools/{pool_id}", params={"workspace_id": "pir13"}
    ).json()
    assert continuation["pool_id"] == pool_id
    assert draft_item_id in continuation["continuation_prompt"]


def test_pir13_python_cli_failing_test_repairs_through_allowlisted_pytest(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_cli_app.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "\n"
        "from cli_app import answer\n"
        "\n"
        "\n"
        "def test_answer_returns_atlas_ok():\n"
        "    assert answer() == \"atlas-ok\"\n",
        encoding="utf-8",
    )
    client = _client(tmp_path, repo, llm_json_fn=_python_cli_repair_llm)

    plan_payload = {
        "root_goal": "Create a Greenfield Python CLI module.",
        "requirements": [
            {
                "id": "REQ-CLI",
                "text": "Provide answer function that returns atlas-ok for the Python CLI.",
            }
        ],
        "implementation_steps": [
            {
                "step_id": "cli",
                "title": "Create cli_app.py",
                "description": "Create a Python CLI module with an answer function.",
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["cli_app.py"],
                "acceptance_criteria": [
                    "Provide answer function that returns atlas-ok for the Python CLI."
                ],
            }
        ],
    }

    created = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Create a Greenfield Python CLI module.",
            "project_path": str(repo),
            "project_name": "pir13-python-cli",
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
            "run_id": "pir13_cli_patchgen",
            "source_type": "plan_item",
        },
    ).json()
    assert proposed["status"] == "proposed", proposed
    assert "return \"wrong\"" in proposed["proposal"]["metadata"]["proposed_content"]

    approved_proposal = client.post(
        "/api/atlas/patch-proposals/decide",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "decision": "approved",
            "reason": "PIR-13 Python CLI scenario approval.",
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
            "run_id": "pir13_cli_draft",
        },
    ).json()
    assert draft["status"] == "created", draft
    draft_item_id = draft["draft_item"]["draft_item_id"]

    approved_item = client.post(
        "/api/atlas/approvals/decide",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "decision": "approved",
            "reason": "Approve the Python CLI PlanItem for Safe Apply.",
        },
    ).json()
    assert approved_item["decision"] == "approved", approved_item

    repaired = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_cli_repair",
            "command_id": "pytest_selected",
            "metadata": {"test_path": "tests/test_cli_app.py"},
        },
    ).json()
    assert repaired["status"] == "applied_and_verified", repaired
    verification = repaired["auto_verification_result"]
    assert verification["status"] == "passed", verification
    assert verification["command_id"] == "pytest_selected"
    assert verification["metadata"]["recovered_by_self_correction"] is True
    self_correction = verification["metadata"]["self_correction_result"]
    assert self_correction["status"] == "recovered"
    assert self_correction["attempts"] == 1
    assert self_correction["metadata"]["final_verification_result"]["command_id"] == "pytest_selected"
    assert "tests/test_cli_app.py" in self_correction["metadata"]["final_verification_result"]["command"]
    assert (repo / "cli_app.py").read_text(encoding="utf-8") == _fixed_python_cli()

    events_path = (
        Path(main.app.state.atlas_ca_data_dir)
        / "atlas"
        / "workspaces"
        / "pir13"
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_cli_repair"
        / "events.ndjson"
    )
    events_text = events_path.read_text(encoding="utf-8")
    assert '"event_type": "auto_verification_failed"' in events_text
    assert '"event_type": "self_correction_recovered"' in events_text
    assert '"event_type": "auto_verification_passed"' in events_text


def test_pir13_fastapi_api_scenario_reaches_real_pytest_probe(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_api.py").write_text(
        "from fastapi.testclient import TestClient\n"
        "\n"
        "from app.main import app\n"
        "\n"
        "\n"
        "def test_health_endpoint_returns_ok():\n"
        "    response = TestClient(app).get(\"/health\")\n"
        "    assert response.status_code == 200\n"
        "    assert response.json() == {\"status\": \"ok\"}\n",
        encoding="utf-8",
    )
    client = _client(tmp_path, repo, llm_json_fn=_fastapi_api_llm)

    plan_payload = {
        "root_goal": "Create a Greenfield FastAPI API.",
        "requirements": [
            {
                "id": "REQ-API",
                "text": "Expose FastAPI app with GET /health returning status ok.",
            }
        ],
        "implementation_steps": [
            {
                "step_id": "api",
                "title": "Create FastAPI health API",
                "description": "Create app/main.py with a FastAPI app and GET /health.",
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["app/main.py"],
                "acceptance_criteria": [
                    "Expose FastAPI app with GET /health returning status ok."
                ],
            }
        ],
    }

    created = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Create a Greenfield FastAPI API.",
            "project_path": str(repo),
            "project_name": "pir13-fastapi-api",
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
            "run_id": "pir13_fastapi_patchgen",
            "source_type": "plan_item",
        },
    ).json()
    assert proposed["status"] == "proposed", proposed
    assert proposed["proposal"]["metadata"]["proposed_content"] == _fastapi_api_main()

    approved_proposal = client.post(
        "/api/atlas/patch-proposals/decide",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "decision": "approved",
            "reason": "PIR-13 FastAPI API scenario approval.",
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
            "run_id": "pir13_fastapi_draft",
        },
    ).json()
    assert draft["status"] == "created", draft
    draft_item_id = draft["draft_item"]["draft_item_id"]

    approved_item = client.post(
        "/api/atlas/approvals/decide",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "decision": "approved",
            "reason": "Approve the FastAPI API PlanItem for Safe Apply.",
        },
    ).json()
    assert approved_item["decision"] == "approved", approved_item

    verified = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_fastapi_verify",
            "command_id": "pytest_selected",
            "metadata": {"test_path": "tests/test_api.py"},
        },
    ).json()
    assert verified["status"] == "applied_and_verified", verified
    assert verified["auto_safe_apply_result"]["status"] == "applied"
    verification = verified["auto_verification_result"]
    assert verification["status"] == "passed", verification
    assert verification["command_id"] == "pytest_selected"
    assert "tests/test_api.py" in verification["command"]
    assert (repo / "app" / "main.py").read_text(encoding="utf-8") == _fastapi_api_main()

    events_path = (
        Path(main.app.state.atlas_ca_data_dir)
        / "atlas"
        / "workspaces"
        / "pir13"
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_fastapi_verify"
        / "events.ndjson"
    )
    events_text = events_path.read_text(encoding="utf-8")
    assert '"event_type": "auto_safe_apply_completed"' in events_text
    assert '"event_type": "auto_verification_passed"' in events_text


def test_pir13_frontend_backend_browser_to_api_flow(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_browser_api.py").write_text(
        "import socket\n"
        "import threading\n"
        "import time\n"
        "\n"
        "import httpx\n"
        "import uvicorn\n"
        "from playwright.sync_api import expect, sync_playwright\n"
        "\n"
        "from app.main import app\n"
        "\n"
        "\n"
        "def _free_port() -> int:\n"
        "    with socket.socket() as sock:\n"
        "        sock.bind((\"127.0.0.1\", 0))\n"
        "        return int(sock.getsockname()[1])\n"
        "\n"
        "\n"
        "def _wait_ready(base_url: str) -> None:\n"
        "    deadline = time.time() + 10\n"
        "    last_error = None\n"
        "    while time.time() < deadline:\n"
        "        try:\n"
        "            response = httpx.get(f\"{base_url}/api/message\", timeout=1.0)\n"
        "            if response.status_code == 200:\n"
        "                return\n"
        "        except Exception as exc:\n"
        "            last_error = exc\n"
        "        time.sleep(0.1)\n"
        "    raise AssertionError(f\"server did not become ready: {last_error}\")\n"
        "\n"
        "\n"
        "def test_browser_fetches_backend_api():\n"
        "    port = _free_port()\n"
        "    base_url = f\"http://127.0.0.1:{port}\"\n"
        "    server = uvicorn.Server(uvicorn.Config(app, host=\"127.0.0.1\", port=port, log_level=\"warning\"))\n"
        "    thread = threading.Thread(target=server.run, daemon=True)\n"
        "    thread.start()\n"
        "    try:\n"
        "        _wait_ready(base_url)\n"
        "        with sync_playwright() as playwright:\n"
        "            browser = playwright.chromium.launch(headless=True)\n"
        "            try:\n"
        "                page = browser.new_page()\n"
        "                page.goto(base_url, wait_until=\"networkidle\")\n"
        "                page.click(\"#load\")\n"
        "                expect(page.locator(\"#message\")).to_have_text(\"atlas browser api ok\")\n"
        "            finally:\n"
        "                browser.close()\n"
        "    finally:\n"
        "        server.should_exit = True\n"
        "        thread.join(timeout=5)\n",
        encoding="utf-8",
    )
    client = _client(tmp_path, repo, llm_json_fn=_frontend_backend_llm)

    plan_payload = {
        "root_goal": "Create a Greenfield frontend and backend browser-to-API app.",
        "requirements": [
            {
                "id": "REQ-BROWSER-API",
                "text": "Browser frontend fetches backend API and displays atlas browser api ok.",
            }
        ],
        "implementation_steps": [
            {
                "step_id": "browser_api",
                "title": "Create frontend/backend FastAPI app",
                "description": "Create app/main.py serving a browser frontend and backend API.",
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["app/main.py"],
                "acceptance_criteria": [
                    "Browser frontend fetches backend API and displays atlas browser api ok."
                ],
            }
        ],
    }

    created = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Create a Greenfield frontend and backend browser-to-API app.",
            "project_path": str(repo),
            "project_name": "pir13-frontend-backend",
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
            "run_id": "pir13_browser_api_patchgen",
            "source_type": "plan_item",
        },
    ).json()
    assert proposed["status"] == "proposed", proposed
    assert proposed["proposal"]["metadata"]["proposed_content"] == _frontend_backend_main()

    approved_proposal = client.post(
        "/api/atlas/patch-proposals/decide",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "decision": "approved",
            "reason": "PIR-13 frontend/backend scenario approval.",
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
            "run_id": "pir13_browser_api_draft",
        },
    ).json()
    assert draft["status"] == "created", draft
    draft_item_id = draft["draft_item"]["draft_item_id"]

    approved_item = client.post(
        "/api/atlas/approvals/decide",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "decision": "approved",
            "reason": "Approve the frontend/backend PlanItem for Safe Apply.",
        },
    ).json()
    assert approved_item["decision"] == "approved", approved_item

    verified = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_browser_api_verify",
            "command_id": "pytest_selected",
            "metadata": {"test_path": "tests/test_browser_api.py"},
        },
    ).json()
    assert verified["status"] == "applied_and_verified", verified
    assert verified["auto_safe_apply_result"]["status"] == "applied"
    verification = verified["auto_verification_result"]
    assert verification["status"] == "passed", verification
    assert verification["command_id"] == "pytest_selected"
    assert "tests/test_browser_api.py" in verification["command"]
    assert (repo / "app" / "main.py").read_text(encoding="utf-8") == _frontend_backend_main()

    events_path = (
        Path(main.app.state.atlas_ca_data_dir)
        / "atlas"
        / "workspaces"
        / "pir13"
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_browser_api_verify"
        / "events.ndjson"
    )
    events_text = events_path.read_text(encoding="utf-8")
    assert '"event_type": "auto_safe_apply_completed"' in events_text
    assert '"event_type": "auto_verification_passed"' in events_text


def test_pir13_fastapi_sqlite_persists_after_reload(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_api_sqlite.py").write_text(
        "import importlib\n"
        "\n"
        "from fastapi.testclient import TestClient\n"
        "\n"
        "import app.main as api_main\n"
        "\n"
        "\n"
        "def test_item_persists_after_module_reload():\n"
        "    first_client = TestClient(api_main.app)\n"
        "    created = first_client.post(\"/items\", json={\"name\": \"atlas\"})\n"
        "    assert created.status_code == 200\n"
        "    assert created.json() == {\"id\": 1, \"name\": \"atlas\"}\n"
        "\n"
        "    reloaded = importlib.reload(api_main)\n"
        "    second_client = TestClient(reloaded.app)\n"
        "    response = second_client.get(\"/items/1\")\n"
        "    assert response.status_code == 200\n"
        "    assert response.json() == {\"id\": 1, \"name\": \"atlas\"}\n",
        encoding="utf-8",
    )
    client = _client(tmp_path, repo, llm_json_fn=_fastapi_sqlite_llm)

    plan_payload = {
        "root_goal": "Create a Greenfield FastAPI API with SQLite persistence.",
        "requirements": [
            {
                "id": "REQ-SQLITE",
                "text": "Persist items in SQLite and return them after FastAPI app reload.",
            }
        ],
        "implementation_steps": [
            {
                "step_id": "sqlite_api",
                "title": "Create SQLite-backed FastAPI API",
                "description": "Create app/main.py with SQLite item create/read endpoints.",
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["app/main.py"],
                "acceptance_criteria": [
                    "Persist items in SQLite and return them after FastAPI app reload."
                ],
            }
        ],
    }

    created = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Create a Greenfield FastAPI API with SQLite persistence.",
            "project_path": str(repo),
            "project_name": "pir13-fastapi-sqlite",
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
            "run_id": "pir13_sqlite_patchgen",
            "source_type": "plan_item",
        },
    ).json()
    assert proposed["status"] == "proposed", proposed
    assert proposed["proposal"]["metadata"]["proposed_content"] == _fastapi_sqlite_main()

    approved_proposal = client.post(
        "/api/atlas/patch-proposals/decide",
        json={
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": "pir13",
            "proposal_id": proposed["proposal"]["proposal_id"],
            "decision": "approved",
            "reason": "PIR-13 FastAPI SQLite scenario approval.",
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
            "run_id": "pir13_sqlite_draft",
        },
    ).json()
    assert draft["status"] == "created", draft
    draft_item_id = draft["draft_item"]["draft_item_id"]

    approved_item = client.post(
        "/api/atlas/approvals/decide",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "decision": "approved",
            "reason": "Approve the FastAPI SQLite PlanItem for Safe Apply.",
        },
    ).json()
    assert approved_item["decision"] == "approved", approved_item

    verified = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": "pir13",
            "run_id": "pir13_sqlite_verify",
            "command_id": "pytest_selected",
            "metadata": {"test_path": "tests/test_api_sqlite.py"},
        },
    ).json()
    assert verified["status"] == "applied_and_verified", verified
    assert verified["auto_safe_apply_result"]["status"] == "applied"
    verification = verified["auto_verification_result"]
    assert verification["status"] == "passed", verification
    assert verification["command_id"] == "pytest_selected"
    assert "tests/test_api_sqlite.py" in verification["command"]
    assert (repo / "app" / "main.py").read_text(encoding="utf-8") == _fastapi_sqlite_main()
    assert (repo / "app" / "atlas_items.sqlite3").exists()

    events_path = (
        Path(main.app.state.atlas_ca_data_dir)
        / "atlas"
        / "workspaces"
        / "pir13"
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_sqlite_verify"
        / "events.ndjson"
    )
    events_text = events_path.read_text(encoding="utf-8")
    assert '"event_type": "auto_safe_apply_completed"' in events_text
    assert '"event_type": "auto_verification_passed"' in events_text
