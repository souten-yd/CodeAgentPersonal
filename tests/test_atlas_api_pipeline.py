from pathlib import Path

from fastapi.testclient import TestClient

import main


API_FILE = Path("app/api/atlas_pipeline.py")


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _create_pool(client: TestClient, goal: str = "Ship Atlas API integration") -> dict:
    response = client.post("/api/atlas/plan-pools", json={"input": goal})
    assert response.status_code == 200, response.text
    return response.json()


def test_create_plan_pool_from_empty_payload_returns_fallback_pool(tmp_path) -> None:
    client = _client(tmp_path)

    body = _create_pool(client)

    assert body["status"] == "ready"
    assert body["pool_id"]
    assert body["item_count"] >= 3
    assert Path(body["checkpoint_path"]).exists()
    item_types = {item["item_type"] for item in body["plan_pool"]["items"]}
    assert {"research", "planning", "verification"}.issubset(item_types)


def test_get_plan_pool(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get(f"/api/atlas/plan-pools/{created['pool_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["pool_id"] == created["pool_id"]
    assert body["root_goal"] == "Ship Atlas API integration"


def test_get_plan_pool_markdown(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get(f"/api/atlas/plan-pools/{created['pool_id']}/markdown")

    assert response.status_code == 200
    markdown = response.json()["markdown"]
    assert "Root Goal" in markdown
    assert "Items" in markdown
    assert created["pool_id"] in markdown


def test_pipeline_dry_run_runs_fallback_pool(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"]
    assert body["pool_id"] == created["pool_id"]
    assert body["status"] in {"completed", "paused", "blocked", "failed", "completed_with_warnings"}
    assert Path(body["checkpoint_path"]).exists()
    assert body["events"]


def test_pipeline_status_requires_pool_id_or_returns_422(tmp_path) -> None:
    client = _client(tmp_path)

    response = client.get("/api/atlas/pipeline/status/run_missing")

    assert response.status_code == 422


def test_pipeline_status_returns_saved_state(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()

    response = client.get(
        f"/api/atlas/pipeline/status/{dry_run['run_id']}",
        params={"pool_id": created["pool_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == dry_run["run_id"]
    assert body["pool_id"] == created["pool_id"]
    assert body["state"]["run_id"] == dry_run["run_id"]
    assert body["events"]


def test_pipeline_status_missing_state_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get(
        "/api/atlas/pipeline/status/run_missing",
        params={"pool_id": created["pool_id"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "pipeline state not found"


def test_recovery_latest_marks_missing_run_state_as_stale(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()
    for state_path in tmp_path.rglob("state.json"):
        if dry_run["run_id"] in str(state_path):
            state_path.unlink()

    response = client.get("/api/atlas/recovery/latest")

    assert response.status_code == 200
    summary = response.json()["recovery_summary"]
    assert summary["pool_id"] == created["pool_id"]
    assert summary["run_id"] == dry_run["run_id"]
    assert summary["status"] == "stale"
    assert "pipeline_state_not_found" in summary["warnings"]
    assert summary["next_action"] == "Start a new dry-run from the recovered PlanPool."


def test_recovery_latest(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()

    response = client.get("/api/atlas/recovery/latest")

    assert response.status_code == 200
    summary = response.json()["recovery_summary"]
    assert summary["pool_id"] == created["pool_id"]
    assert summary["run_id"] == dry_run["run_id"]
    assert summary["status"] in {"completed", "paused", "blocked", "failed", "running", "ready"}


def test_continuation_latest_returns_200(tmp_path) -> None:
    client = _client(tmp_path)

    response = client.get("/api/atlas/continuation/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == "default"
    assert "continuation_prompt" in body


def test_continuation_latest_after_create_plan_includes_pool_id(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get("/api/atlas/continuation/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["pool_id"] == created["pool_id"]
    assert created["pool_id"] in body["continuation_prompt"]


def test_continuation_latest_after_dry_run_includes_run_status(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    dry_run = client.post("/api/atlas/pipeline/dry-run", json={"pool_id": created["pool_id"]}).json()

    response = client.get("/api/atlas/continuation/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == dry_run["run_id"]
    assert body["status"] == dry_run["status"]


def test_continuation_pool_returns_prompt(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)

    response = client.get(f"/api/atlas/continuation/pools/{created['pool_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["pool_id"] == created["pool_id"]
    assert "CodeAgentPersonal / KasaneCore" in body["continuation_prompt"]
    assert "Task = PlanItem" in body["continuation_prompt"]


def test_continuation_api_has_no_execution_side_effect_tokens() -> None:
    source = API_FILE.read_text(encoding="utf-8")

    for forbidden in [
        "requests.",
        "httpx",
        "deep_research_job",
        "safe_apply(",
        "run_command(",
        "subprocess",
    ]:
        assert forbidden not in source


def test_no_task_or_agent_routes_added() -> None:
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    api_source = API_FILE.read_text(encoding="utf-8")

    assert "/api/task/plan" in paths  # existing legacy route, not added by this PR
    assert "/api/task/continue" in paths  # existing legacy route, not added by this PR
    assert "/api/agent/run" not in paths
    assert '"/api/task' not in api_source
    assert '"/api/agent' not in api_source


def test_api_does_not_expose_safe_apply(tmp_path) -> None:
    client = _client(tmp_path)
    created = _create_pool(client)
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}

    assert all("safe_apply" not in path and "safe-apply" not in path for path in paths if path.startswith("/api/atlas/"))
    response = client.post(
        "/api/atlas/pipeline/dry-run",
        json={"pool_id": created["pool_id"], "safe_apply": True},
    )
    assert response.status_code == 200
    assert response.json()["pool_id"] == created["pool_id"]


def test_api_has_no_deep_research_or_web_side_effect_tokens() -> None:
    source = API_FILE.read_text(encoding="utf-8")

    for forbidden in [
        "requests.",
        "httpx",
        "DeepResearch",
        "deep_research_job",
        "safe_apply(",
        "run_command(",
        "subprocess",
    ]:
        assert forbidden not in source


def test_create_plan_pool_auto_falls_back_when_real_planner_unavailable(tmp_path) -> None:
    client = _client(tmp_path)
    if hasattr(main.app.state, "atlas_llm_json_fn"):
        main.app.state.atlas_llm_json_fn = None

    response = client.post("/api/atlas/plan-pools", json={"input": "Bridge fallback", "planner_mode": "auto"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_fallback"] is True
    assert body["planner_status"] == "fallback_used"
    assert "real_planner_unavailable" in body["warnings"]
    assert body["plan_pool"]["metadata"]["source"] == "fallback"


def test_create_plan_pool_fallback_only(tmp_path) -> None:
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _prompt, _schema: {"ok": True}

    response = client.post("/api/atlas/plan-pools", json={"input": "Force fallback", "planner_mode": "fallback_only"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_fallback"] is True
    assert body["plan_pool"]["metadata"]["source"] == "fallback"
    main.app.state.atlas_llm_json_fn = None


def test_create_plan_pool_with_plan_payload_still_works(tmp_path) -> None:
    client = _client(tmp_path)
    payload = {
        "implementation_steps": [
            {"step_id": "step_payload_001", "title": "Payload step", "action_type": "update", "target_files": ["README.md"]}
        ]
    }

    response = client.post("/api/atlas/plan-pools", json={"input": "Use payload", "plan_payload": payload})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_fallback"] is False
    assert body["planner_status"] == "skipped"
    assert body["plan_pool"]["metadata"]["source"] == "plan_payload"
    assert body["plan_pool"]["items"][0]["title"] == "Payload step"


def test_create_plan_pool_does_not_add_task_or_agent_routes() -> None:
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    api_source = API_FILE.read_text(encoding="utf-8")

    assert "/api/agent/run" not in paths
    assert '"/api/task' not in api_source
    assert '"/api/agent' not in api_source


def test_create_plan_pool_does_not_execute_safe_apply_test_debug_deepresearch() -> None:
    sources = API_FILE.read_text(encoding="utf-8") + Path("agent/atlas_planner_bridge.py").read_text(encoding="utf-8")

    for forbidden in [
        "requests.",
        "httpx",
        "DeepResearch",
        "deep_research_job",
        "safe_apply(",
        "run_command(",
        "subprocess",
        "TestCommandRunner(",
        "DebugLoopRunner(",
    ]:
        assert forbidden not in sources


def test_create_plan_pool_waiting_for_clarification_shape_if_mocked(tmp_path, monkeypatch) -> None:
    import app.api.atlas_pipeline as atlas_pipeline
    from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeResult

    class WaitingBridge:
        def __init__(self, **_kwargs) -> None:
            pass

        def create_plan_pool(self, _request):
            return AtlasPlannerBridgeResult(
                status="waiting_for_clarification",
                questions=[{"question_id": "q1", "prompt": "Need target?"}],
                requirement={"requirement_id": "req_wait"},
                warnings=["needs_user_input"],
            )

    monkeypatch.setattr(atlas_pipeline, "AtlasPlannerBridge", WaitingBridge)
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _prompt, _schema: {"ok": True}

    response = client.post("/api/atlas/plan-pools", json={"input": "Needs details", "planner_mode": "real_planner"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "waiting_for_clarification"
    assert body["pool_id"] == ""
    assert body["plan_pool"] == {}
    assert body["questions"] == [{"question_id": "q1", "prompt": "Need target?"}]
    main.app.state.atlas_llm_json_fn = None
