"""Integration: research-first evidence reaches the planner and adversarial critique drives one revision."""
from __future__ import annotations

import json
from pathlib import Path

from agent.task_planning_runner import TaskPlanningRunner


def _make_llm(state):
    def _llm(prompt: str, user_input: str):
        p = prompt.lower()
        if "requirement analyst" in p:
            return {"interpreted_goal": user_input, "task_type": "feature",
                    "functional_requirements": ["f"], "done_definition": ["d"], "out_of_scope": []}
        if "codebase research assistant" in p:
            state["research_repo_context"] = user_input  # capture what research saw
            return {"relevant_files": ["app/server.py"], "existing_patterns": ["reuse router"],
                    "key_findings": ["routes live in app/server.py"], "risks": ["shared state"],
                    "recommended_approach": "extend existing router"}
        if "adversarial plan reviewer" in p:
            # Combined mode (default): one call carries the angles list; each finding self-tags its angle.
            payload = json.loads(user_input)
            angles = payload.get("angles") or ([payload.get("angle")] if payload.get("angle") else [])
            state["critique_angles"].extend(angles)
            # First overall critique: flag a high gap on the security angle to force one revision.
            if not state["revised"]:
                return {"findings": [{"angle": "security", "severity": "high", "title": "missing auth",
                                       "detail": "x", "recommendation": "add auth"}],
                        "angle_risk": "high", "requires_revision": True}
            return {"findings": [], "angle_risk": "low", "requires_revision": False}
        if "planning specialist" in p:
            state["plan_calls"] += 1
            # The planner's repository_context is embedded in user_input; assert research evidence flows in.
            if "Research Evidence" in user_input:
                state["planner_saw_research"] = True
            if "Adversarial Critique" in user_input:
                state["revised"] = True
            return {"selected_architecture": "Incremental",
                    "implementation_steps": [{"title": "add endpoint", "action_type": "create",
                                              "target_files": ["app/api/new.py"], "risk_level": "low"}],
                    "test_plan": ["t"], "rollback_plan": ["r"]}
        return {}
    return _llm


def test_research_and_critique_flow(tmp_path: Path):
    state = {"plan_calls": 0, "planner_saw_research": False, "revised": False,
             "critique_angles": [], "research_repo_context": ""}
    runner = TaskPlanningRunner(ca_data_dir=str(tmp_path), llm_json_fn=_make_llm(state))
    result = runner.run(user_input="add a new endpoint", project_path=str(tmp_path),
                        planning_mode="standard", requirement_mode="auto")

    # Research evidence reached the planner.
    assert state["planner_saw_research"] is True
    assert result["research_findings"]["relevant_files"] == ["app/server.py"]

    # Adversarial critique ran across all angles and forced exactly one revision (2 planner calls).
    assert "security" in state["critique_angles"]
    assert state["revised"] is True
    assert state["plan_calls"] == 2
    assert "plan_revised_after_adversarial_critique" in result["warnings"]

    # Critique is surfaced on the response (post-revision critique is clean, so no findings remain).
    assert result["adversarial_critique"]["angles_evaluated"]


def test_planning_runs_without_llm_research_is_noop(tmp_path: Path):
    # llm_json_fn returns None for everything -> research/critique degrade, planning still completes.
    runner = TaskPlanningRunner(ca_data_dir=str(tmp_path), llm_json_fn=lambda p, u: None)
    result = runner.run(user_input="x", project_path=str(tmp_path), planning_mode="standard", requirement_mode="auto")
    assert result["plan_id"]
    assert result["research_findings"]["warnings"]  # research_no_output or similar


def test_revision_without_steps_keeps_original_and_warns(tmp_path: Path):
    state = {"plan_calls": 0}

    def llm(prompt: str, user_input: str):
        p = prompt.lower()
        if "requirement analyst" in p:
            return {
                "interpreted_goal": "show Hello World in rainbow",
                "task_type": "feature",
                "functional_requirements": ["Hello World"],
                "done_definition": ["rainbow"],
            }
        if "adversarial plan reviewer" in p:
            return {
                "findings": [{"angle": "quality", "severity": "high", "title": "missing detail", "detail": "x", "recommendation": "revise"}],
                "angle_risk": "high",
                "requires_revision": True,
            }
        if "planning specialist" in p:
            state["plan_calls"] += 1
            if state["plan_calls"] == 1:
                return {
                    "selected_architecture": "Incremental",
                    "implementation_steps": [
                        {
                            "title": "Create rainbow HTML",
                            "description": "Create HTML that shows Hello World in rainbow.",
                            "goal": "Show Hello World in rainbow.",
                            "acceptance_criteria": ["Hello World is visible", "Rainbow styling is visible"],
                            "action_type": "create",
                            "risk_level": "low",
                        }
                    ],
                    "test_plan": ["manual check"],
                    "rollback_plan": ["delete file"],
                }
            return {"selected_architecture": "Invalid", "implementation_steps": []}
        return {}

    runner = TaskPlanningRunner(ca_data_dir=str(tmp_path), llm_json_fn=llm)
    result = runner.run(user_input="show Hello World in rainbow", project_path=str(tmp_path), planning_mode="standard", requirement_mode="auto")

    assert result["plan"]["implementation_steps"][0]["description"] == "Create HTML that shows Hello World in rainbow."
    assert "plan_revision_failed_kept_original" in result["warnings"]
    assert result["status"] == "needs_confirmation"
