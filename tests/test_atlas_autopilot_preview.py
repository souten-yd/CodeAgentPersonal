from pathlib import Path

from agent.atlas_autopilot import AtlasAutopilot
from agent.atlas_autopilot_schema import AtlasAutopilotRequest


def test_create_autopilot_plan_preview_and_safety_constraints(tmp_path: Path) -> None:
    autopilot = AtlasAutopilot(ca_data_dir=str(tmp_path))
    req = AtlasAutopilotRequest(
        autopilot_id="auto_preview_1",
        user_goal="Atlasの長期タスク分解を試したい",
        project_path=str(tmp_path),
        project_name="demo",
    )
    before = sorted(p.name for p in tmp_path.iterdir())
    plan = autopilot.create_autopilot_plan(req)
    after = sorted(p.name for p in tmp_path.iterdir())

    assert before == after
    assert isinstance(plan, dict)
    assert len(plan.get("tasks", [])) >= 1
    assert "safety_constraints" in plan


def test_start_preview_status_is_preview_ready_or_planned(tmp_path: Path) -> None:
    autopilot = AtlasAutopilot(ca_data_dir=str(tmp_path))
    req = AtlasAutopilotRequest(autopilot_id="auto_preview_2", user_goal="日本語ゴール")
    result = autopilot.start_preview(req)
    assert result.get("status") in {"preview_ready", "planned"}
    assert len(result.get("tasks", [])) >= 1
