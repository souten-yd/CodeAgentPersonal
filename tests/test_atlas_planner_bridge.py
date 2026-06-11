from pathlib import Path

from agent.atlas_planner_bridge import AtlasPlannerBridge
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest

BRIDGE_FILE = Path("agent/atlas_planner_bridge.py")


class FakeRunner:
    calls = 0
    result = {}
    last_init_kwargs = {}
    last_kwargs = {}

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = dict(kwargs)

    def run(self, **_kwargs) -> dict:
        type(self).calls += 1
        type(self).last_kwargs = dict(_kwargs)
        if isinstance(type(self).result, Exception):
            raise type(self).result
        return dict(type(self).result)


def _request(**kwargs) -> AtlasPlannerBridgeRequest:
    data = {"input": "Add Atlas planner bridge", "project_path": "", "project_name": "CodeAgentPersonal"}
    data.update(kwargs)
    return AtlasPlannerBridgeRequest(**data)


def _fake_llm(_prompt: str, _schema: str) -> dict:
    return {"ok": True}


def _planner_result() -> dict:
    return {
        "status": "planned",
        "requirement_id": "req_123",
        "plan_id": "plan_123",
        "requirement": {"requirement_id": "req_123", "interpreted_goal": "Ship the bridge"},
        "plan": {
            "plan_id": "plan_123",
            "user_goal": "Ship the bridge",
            "implementation_steps": [
                {
                    "step_id": "step_001",
                    "title": "Wire API to bridge",
                    "description": "Use planner bridge in Atlas Create Plan.",
                    "action_type": "update",
                    "target_files": ["app/api/atlas_pipeline.py"],
                    "risk_level": "medium",
                },
                {
                    "step_id": "step_002",
                    "title": "Verify bridge tests",
                    "description": "Check planner bridge conversion.",
                    "action_type": "test",
                    "target_files": ["tests/test_atlas_planner_bridge.py"],
                    "risk_level": "low",
                },
            ],
            "done_definition": ["PlanPool is created from planner output"],
            "rollback_plan": ["Use fallback PlanPool"],
            "constraints": ["Do not execute implementation"],
        },
        "review_result": {"overall_risk": "medium", "warnings": ["review_warning"]},
        "warnings": ["planner_warning"],
        "plan_markdown_path": "ca_data/plans/plan_123.md",
        "requirement_markdown_path": "ca_data/requirements/req_123.md",
        "nexus_context": {"summary": "Nexus context summary"},
    }


def test_bridge_uses_fallback_when_llm_json_fn_missing(tmp_path) -> None:
    bridge = AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=None)

    result = bridge.create_plan_pool(_request(mode="auto"))

    assert result.used_fallback is True
    assert result.status == "fallback_used"
    assert result.pool is not None
    assert result.pool.metadata["source"] == "fallback"
    assert "real_planner_unavailable" in result.warnings


def test_bridge_forces_fallback_only(tmp_path) -> None:
    FakeRunner.calls = 0
    FakeRunner.result = _planner_result()
    bridge = AtlasPlannerBridge(
        ca_data_dir=str(tmp_path),
        llm_json_fn=_fake_llm,
        planning_runner_factory=FakeRunner,
    )

    result = bridge.create_plan_pool(_request(mode="fallback_only"))

    assert result.used_fallback is True
    assert result.pool is not None
    assert result.pool.metadata["source"] == "fallback"
    assert FakeRunner.calls == 0


def test_bridge_runs_real_planner_with_fake_llm(tmp_path) -> None:
    FakeRunner.calls = 0
    FakeRunner.last_kwargs = {}
    FakeRunner.result = _planner_result()
    bridge = AtlasPlannerBridge(
        ca_data_dir=str(tmp_path),
        llm_json_fn=_fake_llm,
        planning_runner_factory=FakeRunner,
    )

    result = bridge.create_plan_pool(_request(mode="auto"))

    assert result.status == "planned"
    assert result.used_fallback is False
    assert result.pool is not None
    assert [item.title for item in result.pool.items] == ["Wire API to bridge", "Verify bridge tests"]
    assert result.pool.items[0].target_files == ["app/api/atlas_pipeline.py"]
    assert result.pool.items[1].item_type == "verification"
    assert result.pool.metadata["source"] == "real_planner"
    assert FakeRunner.calls == 1


def test_bridge_passes_progress_callback_to_runner(tmp_path) -> None:
    FakeRunner.calls = 0
    FakeRunner.last_init_kwargs = {}
    FakeRunner.last_kwargs = {}
    FakeRunner.result = _planner_result()

    def progress_cb(**payload):
        return payload

    bridge = AtlasPlannerBridge(
        ca_data_dir=str(tmp_path),
        llm_json_fn=_fake_llm,
        planning_runner_factory=FakeRunner,
        progress_cb=progress_cb,
    )

    result = bridge.create_plan_pool(_request(mode="auto"))

    assert result.status == "planned"
    assert FakeRunner.last_init_kwargs["progress_cb"] is progress_cb
    assert FakeRunner.last_kwargs["progress_cb"] is progress_cb


def test_bridge_keeps_advisory_out_of_user_input(tmp_path) -> None:
    FakeRunner.calls = 0
    FakeRunner.last_kwargs = {}
    FakeRunner.result = _planner_result()
    bridge = AtlasPlannerBridge(
        ca_data_dir=str(tmp_path),
        llm_json_fn=_fake_llm,
        planning_runner_factory=FakeRunner,
    )

    result = bridge.create_plan_pool(
        _request(
            input="Hello world の HTML を作って",
            planner_context_text_v2="Repo context. DO NOT EXECUTE.",
        )
    )

    assert result.status == "planned"
    assert FakeRunner.last_kwargs["user_input"] == "Hello world の HTML を作って"
    assert "DO NOT EXECUTE" not in FakeRunner.last_kwargs["user_input"]
    assert "DO NOT EXECUTE" in FakeRunner.last_kwargs["advisory_context"]


def test_bridge_handles_planner_exception_with_fallback(tmp_path) -> None:
    FakeRunner.calls = 0
    FakeRunner.result = RuntimeError("planner exploded")
    bridge = AtlasPlannerBridge(
        ca_data_dir=str(tmp_path),
        llm_json_fn=_fake_llm,
        planning_runner_factory=FakeRunner,
    )

    result = bridge.create_plan_pool(_request(mode="real_planner"))

    assert result.used_fallback is True
    assert result.pool is not None
    assert result.pool.metadata["source"] == "fallback"
    assert "planner_bridge_failed" in result.warnings
    assert "planner exploded" in result.fallback_reason


def test_planner_result_to_plan_payload_maps_steps_to_items(tmp_path) -> None:
    bridge = AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=_fake_llm)

    payload = bridge.planner_result_to_plan_payload(_planner_result(), _request())

    steps = payload["implementation_steps"]
    assert payload["root_goal"] == "Ship the bridge"
    assert steps[0]["action_type"] == "update"
    assert steps[0]["target_files"] == ["app/api/atlas_pipeline.py"]
    assert steps[0]["risk_level"] == "medium"
    assert steps[0]["depends_on"] == []
    assert steps[1]["depends_on"] == ["step_001"]
    assert payload["metadata"]["source"] == "real_planner"
    assert "planner_warning" in payload["warnings"]
    assert "review_warning" in payload["warnings"]


def test_planner_result_to_plan_payload_preserves_codegen_contract(tmp_path) -> None:
    bridge = AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=_fake_llm)
    planner_result = _planner_result()
    planner_result["requirement"]["user_input"] = "Original request text"
    planner_result["requirement"]["preserve_behaviors"] = ["Keep existing auth flow"]
    planner_result["requirements"] = [
        {"requirement_id": "req_render", "description": "Render score", "required": True},
        {"requirement_id": "req_persist", "description": "Persist score", "required": True},
    ]
    planner_result["plan"]["selected_architecture"] = "Use existing score service"
    planner_result["plan"]["preserve_behaviors"] = ["Keep existing reset control"]
    planner_result["plan"]["implementation_steps"][0].update(
        {
            "requirement_ids": ["req_render"],
            "acceptance_criteria": ["Score is visible"],
            "expected_changes": ["Update score renderer"],
            "verification_contract": {"contract_id": "browser_dom", "signals": ["score"]},
            "preserve_behaviors": ["Keep reset control"],
        }
    )

    payload = bridge.planner_result_to_plan_payload(planner_result, _request(input="Original request text"))
    step = payload["implementation_steps"][0]

    assert payload["original_user_request"] == "Original request text"
    assert payload["selected_architecture"] == "Use existing score service"
    assert payload["requirements"][1]["requirement_id"] == "req_persist"
    assert payload["preserve_behaviors"] == ["Keep existing reset control"]
    assert step["requirement_ids"] == ["req_render"]
    assert step["acceptance_criteria"] == ["Score is visible"]
    assert step["expected_changes"] == ["Update score renderer"]
    assert step["verification_contract"]["contract_id"] == "browser_dom"
    assert step["preserve_behaviors"] == ["Keep reset control"]


def test_full_autopilot_payload_repairs_missing_requirement_and_verification_contracts(tmp_path) -> None:
    bridge = AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=_fake_llm)
    planner_result = {
        "status": "planned",
        "requirements": [
            {"requirement_id": "req_heading", "description": "index.html renders Atlas Existing Project Ready"},
            {"requirement_id": "req_status", "description": "index.html displays a visible ready status"},
        ],
        "plan": {
            "user_goal": "Update existing HTML app",
            "implementation_steps": [
                {
                    "step_id": "step_1",
                    "title": "Modify index.html",
                    "description": "Update the existing page heading and visible status.",
                    "action_type": "modify",
                    "target_files": ["index.html"],
                    "risk_level": "low",
                    "acceptance_criteria": ["Atlas Existing Project Ready is visible"],
                }
            ],
            "test_plan": ["Inspect index.html for the heading and visible ready status."],
        },
    }

    payload = bridge.planner_result_to_plan_payload(
        planner_result,
        _request(automation_level="full_autopilot"),
    )
    step = payload["implementation_steps"][0]

    assert step["action_type"] == "modify"
    assert step["requirement_ids"] == ["req_heading", "req_status"]
    assert step["verification_contract"]["contract_id"] == "planner_derived_verification"
    assert step["verification_contract"]["source"] == "planner_bridge_full_autopilot_repair"


def test_waiting_for_clarification_result_is_preserved(tmp_path) -> None:
    FakeRunner.calls = 0
    FakeRunner.result = {
        "status": "waiting_for_clarification",
        "questions": [{"question_id": "q1", "prompt": "Which target file?"}],
        "requirement": {"requirement_id": "req_wait"},
        "warnings": ["needs_user_input"],
    }
    bridge = AtlasPlannerBridge(
        ca_data_dir=str(tmp_path),
        llm_json_fn=_fake_llm,
        planning_runner_factory=FakeRunner,
    )

    result = bridge.create_plan_pool(_request(mode="real_planner"))

    assert result.status == "waiting_for_clarification"
    assert result.pool is None
    assert result.questions == [{"question_id": "q1", "prompt": "Which target file?"}]
    assert result.used_fallback is False
    assert FakeRunner.calls == 1


def test_bridge_has_no_runtime_execution_side_effect_tokens() -> None:
    source = BRIDGE_FILE.read_text(encoding="utf-8")

    for forbidden in [
        "subprocess",
        "safe_apply(",
        "run_command(",
        "TestCommandRunner(",
        "DebugLoopRunner(",
        "DeepResearch",
        "deep_research_job",
        "requests.",
        "httpx",
    ]:
        assert forbidden not in source
