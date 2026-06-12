import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.server import create_app
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_SHADOW, RolloutConfig
from agent.project_intelligence.service_registry import (
    close_project_intelligence_service,
    register_project_intelligence_service,
)


API_FILE = Path("app/api/atlas_pipeline.py")


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _create_pool(client: TestClient, goal: str = "Ship Atlas API integration") -> dict:
    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": goal})
    assert response.status_code == 200, response.text
    return response.json()


def test_create_plan_pool_from_empty_payload_returns_fallback_pool(tmp_path) -> None:
    client = _client(tmp_path)

    body = _create_pool(client)

    assert body["status"] in {"ready", "approval_required"}
    assert body["pool_id"]
    assert body["item_count"] >= 0
    assert Path(body["checkpoint_path"]).exists()
    assert body["orchestration_summary"]["phase"] in {"plan_ready", "approval_required"}
    assert body["orchestration_summary"]["phase"]
    item_types = {item["item_type"] for item in body["plan_pool"]["items"]}
    assert item_types or body["plan_pool"]["metadata"].get("planner_failure_requires_replan") is True


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
    assert body["orchestration_summary"]["pool_id"] == created["pool_id"]
    assert body["orchestration_summary"]["phase"] in {"completed", "approval_required", "blocked", "failed", "running", "dependency_waiting"}
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
    payload = response.json()
    summary = payload["recovery_summary"]
    assert summary["pool_id"] == created["pool_id"]
    assert summary["run_id"] == dry_run["run_id"]
    assert summary["status"] == "stale"
    assert "pipeline_state_not_found" in summary["warnings"]
    assert summary["next_action"] == "Start a new dry-run from the recovered PlanPool."
    assert payload["orchestration_summary"]["is_stale"] is True
    assert payload["orchestration_summary"]["can_start_dry_run"] is True


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



def test_api_has_no_deep_research_or_web_side_effect_tokens() -> None:
    source = API_FILE.read_text(encoding="utf-8")

    for forbidden in [
        "requests.",
        "httpx",
        "DeepResearch",
        "deep_research_job",
                "run_command(",
        "subprocess",
    ]:
        assert forbidden not in source


def test_create_plan_pool_auto_falls_back_when_real_planner_unavailable(tmp_path) -> None:
    client = _client(tmp_path)
    if hasattr(main.app.state, "atlas_llm_json_fn"):
        main.app.state.atlas_llm_json_fn = None

    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "Bridge fallback", "planner_mode": "auto"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["planner_status"] in {"planned", "fallback_used", "skipped"}
    assert isinstance(body["warnings"], list)
    assert body["plan_pool"]["metadata"]["source"] in {"fallback", "real_planner"}


def test_create_plan_pool_fallback_only(tmp_path) -> None:
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _prompt, _schema: {"ok": True}

    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "Force fallback", "planner_mode": "fallback_only"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_pool"]["metadata"]["source"] in {"fallback", "real_planner"}
    main.app.state.atlas_llm_json_fn = None


def test_create_plan_pool_with_plan_payload_still_works(tmp_path) -> None:
    client = _client(tmp_path)
    payload = {
        "implementation_steps": [
            {"step_id": "step_payload_001", "title": "Payload step", "action_type": "update", "target_files": ["README.md"]}
        ]
    }

    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "Use payload", "plan_payload": payload})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_fallback"] is False
    assert body["planner_status"] == "skipped"
    assert body["plan_pool"]["metadata"]["source"] == "plan_payload"
    assert body["plan_pool"]["items"][0]["title"] == "Payload step"


def test_create_plan_pool_persists_project_intelligence_shadow_metadata(tmp_path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    register_project_intelligence_service(
        app,
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_SHADOW: "1"}),
    )
    try:
        payload = {"implementation_steps": [{"step_id": "step_pi", "title": "PI step", "target_files": ["a.py"]}]}
        response = TestClient(app).post(
            "/api/atlas/plan-pools?sync=1",
            json={
                "input": "Use PI shadow context",
                "plan_payload": payload,
                "project_path": str(tmp_path / "repo"),
                "target_files": ["a.py"],
            },
        )
    finally:
        close_project_intelligence_service(app)

    assert response.status_code == 200, response.text
    metadata = response.json()["plan_pool"]["metadata"]
    pi = metadata["project_intelligence_planning"]
    assert pi["mode"] == "shadow"
    assert pi["used_intelligence"] is False
    assert pi["shadow_artifact"]["manifest_id"]
    assert metadata["context_manifest_id"] == pi["manifest_id"]


def test_create_plan_pool_active_project_intelligence_uses_ready_existing_context(tmp_path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print('existing')\n", encoding="utf-8")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_a.py").write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    register_project_intelligence_service(
        app,
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}),
    )
    try:
        payload = {
            "implementation_steps": [
                {
                    "step_id": "step_pi",
                    "title": "Update existing implementation file",
                    "description": "Update the existing implementation file with the requested behavior while preserving tests.",
                    "action_type": "update",
                    "target_files": ["a.py"],
                    "acceptance_criteria": ["Existing tests remain runnable after the update."],
                }
            ]
        }
        response = TestClient(app).post(
            "/api/atlas/plan-pools?sync=1",
            json={
                "input": "Use PI active context",
                "plan_payload": payload,
                "project_path": str(repo),
                "target_files": ["a.py"],
            },
        )
    finally:
        close_project_intelligence_service(app)

    assert response.status_code == 200, response.text
    body = response.json()
    metadata = body["plan_pool"]["metadata"]
    pi = metadata["project_intelligence_planning"]
    assert pi["mode"] == "active"
    assert pi["used_intelligence"] is True
    assert pi["readiness"] == "ready"
    assert pi["stale"] is False
    assert pi["project_mode"] == "existing"
    assert pi["refs"]["actual_twin_revision_id"]
    assert pi["blocking"] is False
    assert pi["blocking_reason"] == ""
    assert "plan_revision_required" not in metadata
    assert "project_intelligence_block_reason" not in metadata
    assert "project_intelligence_stale_context_blocks_active_planning" not in body["plan_pool"]["warnings"]


def test_create_plan_pool_active_project_intelligence_uses_ready_greenfield_context(tmp_path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    register_project_intelligence_service(
        app,
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}),
    )
    try:
        payload = {
            "implementation_steps": [
                {
                    "step_id": "step_pi",
                    "title": "Create greenfield implementation file",
                    "description": "Create the initial implementation file for the greenfield workspace.",
                    "action_type": "create",
                    "target_files": ["a.py"],
                    "acceptance_criteria": ["The new implementation file exists with the requested behavior."],
                }
            ]
        }
        response = TestClient(app).post(
            "/api/atlas/plan-pools?sync=1",
            json={
                "input": "Use PI active context for greenfield",
                "plan_payload": payload,
                "project_path": str(repo),
                "target_files": ["a.py"],
            },
        )
    finally:
        close_project_intelligence_service(app)

    assert response.status_code == 200, response.text
    body = response.json()
    metadata = body["plan_pool"]["metadata"]
    pi = metadata["project_intelligence_planning"]
    assert pi["mode"] == "active"
    assert pi["used_intelligence"] is True
    assert pi["readiness"] == "ready"
    assert pi["stale"] is False
    assert pi["project_mode"] == "empty"
    assert pi["blocking"] is False
    assert pi["blocking_reason"] == ""
    assert pi["degraded_reason"] == ""
    assert "plan_revision_required" not in metadata
    assert "project_intelligence_block_reason" not in metadata
    assert body["plan_pool"]["status"] == "ready"
    assert "project_intelligence_stale_context_blocks_active_planning" not in body["plan_pool"]["warnings"]
    assert "project_intelligence_stale_context_recorded_non_blocking_greenfield" not in body["plan_pool"]["warnings"]


def test_project_intelligence_stale_context_blocking_policy_preserves_greenfield_escape() -> None:
    import app.api.atlas_pipeline as atlas_pipeline

    assert (
        atlas_pipeline._stale_project_intelligence_blocks_planning(
            mode="active",
            stale=True,
            project_mode="existing",
        )
        is True
    )
    assert (
        atlas_pipeline._stale_project_intelligence_blocks_planning(
            mode="active",
            stale=True,
            project_mode="empty",
        )
        is False
    )
    assert (
        atlas_pipeline._stale_project_intelligence_blocks_planning(
            mode="active",
            stale=True,
            project_mode="greenfield_partial",
        )
        is False
    )


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

    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "Needs details", "planner_mode": "real_planner"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "waiting_for_clarification"
    assert body["pool_id"] == ""
    assert body["plan_pool"] == {}
    assert body["questions"] == [{"question_id": "q1", "prompt": "Need target?"}]
    assert body["orchestration_summary"]["requires_clarification"] is True
    assert body["orchestration_summary"]["phase"] == "clarification_required"
    main.app.state.atlas_llm_json_fn = None


def test_api_still_does_not_expose_runner_execution_controls() -> None:
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    atlas_paths = [path.lower() for path in paths if path.startswith("/api/atlas/")]

    for forbidden in ("test-command", "testcommand", "debug-loop", "debugloop", "deep-research", "deepresearch"):
        assert all(forbidden not in path for path in atlas_paths)
    assert any("safe-apply/execute" in path for path in atlas_paths)


def test_create_plan_pool_uses_registered_atlas_llm_json_fn(tmp_path) -> None:
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _s, _u: {"plan": {"implementation_steps": [{"title": "x"}]}, "status": "planned"}
    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "goal", "planner_mode": "real_planner"})
    assert response.status_code == 200
    body = response.json()
    assert body["used_fallback"] is False
    assert body["plan_pool"]["metadata"]["source"] == "real_planner"


def test_create_plan_pool_records_forge_bridge_decision_at_llm_boundary(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FORGE_ENABLED", raising=False)
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _s, _u: {"plan": {"implementation_steps": [{"title": "x"}]}, "status": "planned"}

    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "goal", "planner_mode": "real_planner"})

    assert response.status_code == 200
    event_files = list((tmp_path / "model_forge" / "execution_bridge").glob("planning.*.json"))
    assert event_files
    event = json.loads(event_files[-1].read_text(encoding="utf-8"))
    assert event["stage"] == "planning"
    assert event["task_category"] == "plan_pool_create"
    assert event["decision"] == "forge_disabled_legacy_primary"
    assert event["legacy_primary"] is True
    assert event["changes_production_routing"] is False


def test_create_plan_pool_cutover_returns_forge_output_at_llm_boundary(tmp_path, monkeypatch) -> None:
    import app.api.atlas_pipeline as atlas_pipeline
    from agent.model_forge.profile_store import ProfileStore
    from agent.model_forge.provider_base import ForgeProvider, HealthState, ProviderHealth
    from agent.model_forge.provider_registry import ProviderRegistry
    from agent.model_forge.schema import ForgeExecutionResult, ProviderDescriptor, ProviderSupport, SourceClass
    from agent.model_forge.shadow import ShadowStore
    from agent.model_forge.source_policy import SourceMode
    from agent.model_forge.stage_matrix import StageMatrix
    from agent.model_forge.stage_taxonomy import ForgeStage, StageMode

    class _Provider(ForgeProvider):
        def __init__(self) -> None:
            super().__init__(
                ProviderDescriptor(
                    provider_id="fake_local",
                    provider_type="fake",
                    source_class=SourceClass.SELF_HOSTED,
                    enabled=True,
                    supports=ProviderSupport(chat_completions=True),
                )
            )

        def _probe_health(self) -> ProviderHealth:
            return ProviderHealth(provider_id=self.provider_id, state=HealthState.READY)

        def run_and_capture(self, request):
            output = json.dumps({"implementation_steps": [{"title": "forge"}], "status": "planned"})
            return (
                ForgeExecutionResult(
                    request_id=request.request_id,
                    provider_id=self.provider_id,
                    model_id="fake-model",
                    route_id=request.route_id,
                    stage=request.stage,
                    contract_valid=True,
                ),
                output,
            )

        def execute_chat_completion(self, request):
            result, _output = self.run_and_capture(request)
            return result

    class _Cutover:
        def load(self, stage):
            return {
                "stage": str(stage),
                "status": "active",
                "mode": "auto_select",
                "forge_primary": True,
                "legacy_fallback": True,
            }

    class _Service:
        def __init__(self, ca_data_root, *, prompt_resolver=None, env=None) -> None:
            self.root = Path(ca_data_root)
            self.registry = ProviderRegistry()
            self.registry.register(_Provider())
            self.stage_matrix = StageMatrix(self.root / "model_forge" / "stage_policy.json")
            self.stage_matrix.set_policy(
                ForgeStage.PLANNING,
                StageMode.AUTO_SELECT,
                allow_production_routing=True,
                reason="test_cutover",
            )
            self.profiles = ProfileStore(self.root / "model_forge" / "profiles")
            self.shadow = ShadowStore(self.root / "model_forge" / "shadow")
            self.cutover_controller = _Cutover()

        def forge_enabled(self) -> bool:
            return True

        def source_mode(self):
            return SourceMode.LOCAL_ONLY

        def models(self) -> list[dict]:
            return [{"provider_id": "fake_local", "model_id": "fake-model", "source": "test"}]

        def record_execution_bridge_event(self, payload: dict) -> str:
            path = self.root / "model_forge" / "execution_bridge" / f"{payload['stage']}.{payload['request_id']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(path)

    monkeypatch.setattr(atlas_pipeline, "ForgeService", _Service)
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _s, _u: {"plan": {"implementation_steps": [{"title": "legacy"}]}, "status": "planned"}

    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "goal", "planner_mode": "real_planner"})

    assert response.status_code == 200
    body = response.json()
    assert body["plan_pool"]["items"][0]["title"] == "forge"
    event_files = list((tmp_path / "model_forge" / "execution_bridge").glob("planning.*.json"))
    assert event_files
    event = json.loads(event_files[-1].read_text(encoding="utf-8"))
    assert event["decision"] == "forge_primary_returned"
    assert event["legacy_primary"] is False
    assert event["changes_production_routing"] is True


def test_create_plan_pool_falls_back_when_llm_json_fn_returns_none(tmp_path) -> None:
    client = _client(tmp_path)
    main.app.state.atlas_llm_json_fn = lambda _s, _u: (_ for _ in ()).throw(RuntimeError("llm unavailable"))
    response = client.post("/api/atlas/plan-pools?sync=1", json={"input": "goal", "planner_mode": "real_planner"})
    assert response.status_code == 200
    body = response.json()
    assert body["fallback_reason"] or body["plan_pool"]["metadata"].get("planner_failure_requires_replan") is True


def test_app_registers_atlas_llm_json_fn_without_overwriting_existing(tmp_path) -> None:
    from app.api.atlas_pipeline import register_atlas_llm_json_adapter

    class _State:
        atlas_llm_json_fn = staticmethod(lambda _s, _u: {"keep": True})

    class _App:
        state = _State()

    app = _App()
    before = app.state.atlas_llm_json_fn
    register_atlas_llm_json_adapter(app)
    assert app.state.atlas_llm_json_fn is before
