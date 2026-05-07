from pathlib import Path

from agent.task_planning_runner import TaskPlanningRunner


def _llm(_prompt: str, user_input: str):
    if "deep planning specialist" in _prompt.lower():
        return {
            "user_goal": "goal",
            "requirement_summary": "summary",
            "selected_option_id": "B",
            "architecture_options": [
                {"option_id": "A", "title": "A", "summary": "a", "why_rejected": "too narrow"},
                {"option_id": "B", "title": "B", "summary": "b", "why_selected": "best balance"},
                {"option_id": "C", "title": "C", "summary": "c", "why_rejected": "too large"},
            ],
            "reflection": {"safety_notes": ["plan only"]},
            "verification_strategy": ["check"],
            "done_definition": ["done"],
        }
    if "planning specialist" in _prompt.lower():
        return {
            "architecture_options": ["Incremental"],
            "selected_architecture": "Incremental",
            "implementation_steps": [{"title": "inspect", "action_type": "inspect", "risk_level": "low"}],
            "test_plan": ["t"],
            "rollback_plan": ["r"],
        }
    return {"interpreted_goal": user_input, "task_type": "feature", "functional_requirements": ["f"], "done_definition": ["d"]}


def test_task_planning_runner_uses_deep_planner_for_deep_nexus(tmp_path: Path):
    runner = TaskPlanningRunner(ca_data_dir=str(tmp_path), llm_json_fn=_llm)
    result = runner.run(user_input="deep", project_path=str(tmp_path), planning_mode="deep_nexus")
    assert result["effective_execution_mode"] == "plan_only"
    assert result["plan"]["deep_planning"] is not None
    assert result["review_result"] is not None
    assert Path(result["plan_markdown_path"]).exists()
    assert Path(tmp_path / "plans" / f"{result['plan_id']}.plan.json").exists()
