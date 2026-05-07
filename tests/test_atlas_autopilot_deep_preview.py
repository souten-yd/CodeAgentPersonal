from pathlib import Path

from agent.atlas_autopilot import AtlasAutopilot
from agent.atlas_autopilot_schema import AtlasAutopilotRequest


def test_autopilot_preview_contains_deep_planning_and_execution_order(tmp_path: Path) -> None:
    called = {"n": 0}

    def fake_llm(_prompt: str, _planner_input: str):
        called["n"] += 1
        return {
            "selected_option_id": "B",
            "implementation_phases": ["Requirement refinement", "Implementation plan preparation", "Verification strategy preparation"],
            "verification_strategy": ["Keep preview-only"],
            "done_definition": ["Task breakdown is visible"],
        }

    autopilot = AtlasAutopilot(ca_data_dir=str(tmp_path), llm_json_fn=fake_llm)
    req = AtlasAutopilotRequest(autopilot_id="auto_dp_1", user_goal="atlas goal", project_path=str(tmp_path))
    before = sorted(p.name for p in tmp_path.iterdir())
    out = autopilot.start_preview(req)
    after = sorted(p.name for p in tmp_path.iterdir())

    assert called["n"] >= 1
    assert out["status"] == "preview_ready"
    assert out.get("deep_planning")
    assert len(out.get("tasks", [])) >= 2
    assert out.get("execution_order")
    assert out.get("autopilot_plan", {}).get("preview_only") is True
    assert before == after
