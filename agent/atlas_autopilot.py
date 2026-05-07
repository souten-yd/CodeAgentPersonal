from __future__ import annotations

import uuid
from typing import Callable

from agent.atlas_autopilot_schema import AtlasAutopilotPlan, AtlasAutopilotRequest, AtlasAutopilotRunState
from agent.atlas_task_decomposer import AtlasTaskDecomposer
from agent.deep_planner import DeepPlanner
from agent.requirement_schema import RequirementDefinition


class AtlasAutopilot:
    """Preview-only orchestrator skeleton for Atlas Autopilot."""

    def __init__(
        self,
        *,
        ca_data_dir: str = "",
        planning_runner=None,
        llm_json_fn: Callable[[str, str], dict | None] | None = None,
        deep_planner: DeepPlanner | None = None,
        task_decomposer: AtlasTaskDecomposer | None = None,
    ) -> None:
        self.ca_data_dir = ca_data_dir
        self.planning_runner = planning_runner
        self.llm_json_fn = llm_json_fn or (lambda _prompt, _input: None)
        self.deep_planner = deep_planner or DeepPlanner(self.llm_json_fn)
        self.task_decomposer = task_decomposer or AtlasTaskDecomposer(self.llm_json_fn)
        self._states: dict[str, AtlasAutopilotRunState] = {}

    def create_autopilot_plan(self, request: AtlasAutopilotRequest) -> dict:
        goal = (request.user_goal or "").strip() or "Clarify Atlas Autopilot goal"
        requirement = RequirementDefinition(
            requirement_id=f"auto_req_{request.autopilot_id}",
            source_task_id=request.autopilot_id,
            user_input=request.user_goal,
            project_name=request.project_name,
            project_path=request.project_path,
            resolved_project_path=request.project_path,
            interpreted_goal=f"Atlas Autopilot preview plan for: {goal}",
            assumptions=["Preview-only mode is active; no file edits are executed."],
            constraints=["No auto-approve or auto-apply."],
            done_definition=["Autopilot preview returns task decomposition for Atlas Core."],
        )
        deep_plan = self.deep_planner.build_deep_plan(
            requirement=requirement,
            prompt="Decompose large goal into Atlas task candidates.",
            nexus_context={} if request.use_nexus else {},
            repository_context=f"project={request.project_name or 'unknown'} path={request.project_path or 'unset'}",
        )
        tasks = self.task_decomposer.decompose(
            autopilot_id=request.autopilot_id,
            user_goal=request.user_goal,
            deep_plan=deep_plan,
            project_path=request.project_path,
            project_name=request.project_name,
        )
        selected = next((o for o in deep_plan.architecture_options if o.option_id == deep_plan.selected_option_id), None)
        plan = AtlasAutopilotPlan(
            autopilot_id=request.autopilot_id,
            user_goal=request.user_goal,
            interpreted_goal=requirement.interpreted_goal,
            tasks=tasks,
            assumptions=deep_plan.reflection.assumptions,
            risks=[*deep_plan.reflection.unresolved_questions],
            safety_constraints=deep_plan.reflection.safety_notes or ["No direct file edits by Agent runtime."],
            done_definition=deep_plan.done_definition,
            deep_planning=deep_plan.model_dump(),
            selected_architecture_summary=(selected.summary if selected else ""),
            task_decomposition_strategy="DeepPlanner implementation phases are converted into serial Atlas tasks.",
            execution_order=[t.task_id for t in tasks],
            preview_only=True,
        )
        self._states[request.autopilot_id] = AtlasAutopilotRunState(
            autopilot_id=request.autopilot_id,
            status="planned",
            summary="Preview plan created. No execution was performed.",
            warnings=self.deep_planner.get_last_warnings(),
        )
        return plan.model_dump()

    def start_preview(self, request: AtlasAutopilotRequest) -> dict:
        plan = self.create_autopilot_plan(request)
        prev_warnings = self._states.get(request.autopilot_id).warnings if self._states.get(request.autopilot_id) else []
        state = AtlasAutopilotRunState(
            autopilot_id=request.autopilot_id,
            status="preview_ready",
            blocked_task_ids=["execution_not_supported_in_preview"],
            warnings=[*prev_warnings, "Preview only: execution is disabled in this PR."],
            summary="Atlas Autopilot preview generated. No files were changed.",
        )
        self._states[request.autopilot_id] = state
        return {
            "autopilot_id": request.autopilot_id,
            "status": state.status,
            "message": state.summary,
            "autopilot_plan": plan,
            "deep_planning": plan.get("deep_planning"),
            "tasks": plan.get("tasks", []),
            "execution_order": plan.get("execution_order", []),
            "safety_constraints": plan.get("safety_constraints", []),
            "warnings": state.warnings,
        }

    def get_state(self, autopilot_id: str) -> dict:
        state = self._states.get(autopilot_id)
        if state is None:
            state = AtlasAutopilotRunState(autopilot_id=autopilot_id, status="draft", summary="No state found. Preview has not started.")
        return state.model_dump()
