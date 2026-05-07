from __future__ import annotations

from typing import Callable

from agent.agent_prompts import DEEP_PLAN_GENERATION_PROMPT
from agent.atlas_autopilot_schema import AtlasAutopilotPlan, AtlasAutopilotRequest, AtlasAutopilotRunState
from agent.atlas_execution_preview import AtlasExecutionPreview
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
        execution_preview=None,
        plan_storage=None,
    ) -> None:
        self.ca_data_dir = ca_data_dir
        self.planning_runner = planning_runner
        self.llm_json_fn = llm_json_fn or (lambda _prompt, _input: None)
        self.deep_planner = deep_planner or DeepPlanner(self.llm_json_fn)
        self.task_decomposer = task_decomposer or AtlasTaskDecomposer(self.llm_json_fn)
        self.plan_storage = plan_storage
        self.execution_preview = execution_preview or AtlasExecutionPreview(plan_storage=plan_storage)
        self._states: dict[str, AtlasAutopilotRunState] = {}
        self._plans: dict[str, AtlasAutopilotPlan] = {}

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
            prompt=DEEP_PLAN_GENERATION_PROMPT,
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
            project_path=request.project_path,
            project_name=request.project_name,
        )
        self._plans[request.autopilot_id] = plan
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
        return {"autopilot_id": request.autopilot_id, "status": state.status, "message": state.summary, "autopilot_plan": plan, "deep_planning": plan.get("deep_planning"), "tasks": plan.get("tasks", []), "execution_order": plan.get("execution_order", []), "safety_constraints": plan.get("safety_constraints", []), "warnings": state.warnings}

    def get_state(self, autopilot_id: str) -> dict:
        state = self._states.get(autopilot_id)
        if state is None:
            state = AtlasAutopilotRunState(autopilot_id=autopilot_id, status="draft", summary="No state found. Preview has not started.")
        return state.model_dump()

    def get_plan(self, autopilot_id: str) -> dict:
        plan = self._plans.get(autopilot_id)
        if plan is None:
            return {"autopilot_id": autopilot_id, "status": "not_found", "message": "Autopilot plan was not found. Create Autopilot Preview first.", "autopilot_plan": {}}
        return {"autopilot_id": autopilot_id, "status": "ok", "autopilot_plan": plan.model_dump()}

    def generate_plan_for_task(self, *, autopilot_id: str, task_id: str, project_path: str = "", project_name: str = "", use_nexus: bool = True, planning_mode: str | None = None, requirement_mode: str | None = None) -> dict:
        plan = self._plans.get(autopilot_id)
        if plan is None:
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "not_found", "message": "Autopilot plan or task was not found. Create Autopilot Preview first."}
        task = next((t for t in plan.tasks if t.task_id == task_id), None)
        if task is None:
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "not_found", "message": "Autopilot plan or task was not found. Create Autopilot Preview first."}
        if self.planning_runner is None:
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "planner_unavailable", "message": "TaskPlanningRunner is not configured for Atlas Autopilot."}

        acceptance = "\n".join([f"- {c}" for c in (task.acceptance_criteria or ["Atlas plan is generated with plan-only safety."])])
        task_prompt = (
            f"Atlas Autopilot Task\nTitle: {task.title}\nGoal: {task.goal}\nDescription: {task.description}\nRationale: {task.rationale}\nExpected Output: {task.expected_output}\nAcceptance Criteria:\n{acceptance}\nSafety:\n- This is plan-only. Do not implement yet."
        )
        resolved_project_path = project_path or plan.project_path or ""
        resolved_project_name = project_name or plan.project_name or ""
        planning_result = self.planning_runner.run(
            user_input=task_prompt,
            project_path=resolved_project_path,
            project_name=resolved_project_name,
            planning_mode=planning_mode or task.suggested_planning_mode or "standard",
            requirement_mode=requirement_mode or task.suggested_requirement_mode or "ask_when_needed",
            execution_mode="plan_only",
            use_nexus=use_nexus,
        )
        requirement_id = str((planning_result or {}).get("requirement_id") or "")
        plan_id = str((planning_result or {}).get("plan_id") or "")
        task.linked_requirement_id = requirement_id
        task.linked_plan_id = plan_id
        task.plan_status = str((planning_result or {}).get("status") or "planned")
        task.review_status = str(((planning_result or {}).get("review_result") or {}).get("overall_risk") or "")
        task.last_plan_message = str((planning_result or {}).get("message") or "")
        task.plan_markdown_path = str((planning_result or {}).get("plan_markdown_path") or "")
        task.requirement_markdown_path = str((planning_result or {}).get("requirement_markdown_path") or "")

        state = self._states.get(autopilot_id) or AtlasAutopilotRunState(autopilot_id=autopilot_id, status="planned")
        if task_id not in state.planned_task_ids:
            state.planned_task_ids.append(task_id)
        if plan_id:
            state.task_plan_ids[task_id] = plan_id
        if requirement_id:
            state.task_requirement_ids[task_id] = requirement_id
        state.current_task_id = task_id
        state.status = "task_plan_ready"
        state.summary = "Atlas plan generated for Autopilot task. No implementation was executed."
        self._states[autopilot_id] = state
        self._plans[autopilot_id] = plan
        return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "task_plan_ready", "message": state.summary, "requirement_id": requirement_id, "plan_id": plan_id, "planning_result": planning_result, "task": task.model_dump(), "warnings": (planning_result or {}).get("warnings") or []}

    def prepare_execution_preview_for_task(self, *, autopilot_id: str, task_id: str, project_path: str = "", project_name: str = "", require_approval: bool = True) -> dict:
        plan = self._plans.get(autopilot_id)
        if plan is None:
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "not_found", "message": "Autopilot plan or task was not found. Create Autopilot Preview first."}
        task = next((t for t in plan.tasks if t.task_id == task_id), None)
        if task is None:
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "not_found", "message": "Autopilot plan or task was not found. Create Autopilot Preview first."}
        if not task.linked_plan_id:
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "plan_required", "message": "Plan generation is required before preparing execution preview.", "task": task.model_dump()}

        approval = None
        if self.plan_storage and hasattr(self.plan_storage, "find_latest_approval_for_plan"):
            approval = self.plan_storage.find_latest_approval_for_plan(task.linked_plan_id)
        approved = bool(approval and approval.get("approved_for_execution") is True and approval.get("execution_ready") is True)
        if require_approval and not approved:
            task.approval_status = "approval_required"
            task.execution_preview_status = "approval_required"
            task.last_execution_preview_message = "Plan approval is required before preparing execution preview."
            state = self._states.get(autopilot_id) or AtlasAutopilotRunState(autopilot_id=autopilot_id)
            if task_id not in state.approval_required_task_ids:
                state.approval_required_task_ids.append(task_id)
            state.status = "approval_required"
            self._states[autopilot_id] = state
            return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "approval_required", "message": task.last_execution_preview_message, "plan_id": task.linked_plan_id, "task": task.model_dump()}

        preview = self.execution_preview.prepare_preview(plan_id=task.linked_plan_id, requirement_id=task.linked_requirement_id, approval=approval, project_path=project_path or plan.project_path or "", project_name=project_name or plan.project_name or "")
        task.execution_preview_id = str(preview.get("execution_preview_id") or "")
        task.execution_preview_status = str(preview.get("status") or "execution_preview_ready")
        task.execution_preview_summary = str(preview.get("summary") or "")
        task.last_execution_preview_message = task.execution_preview_summary
        task.approval_status = "approved" if approved else "not_required"
        state = self._states.get(autopilot_id) or AtlasAutopilotRunState(autopilot_id=autopilot_id)
        if task_id not in state.execution_preview_task_ids:
            state.execution_preview_task_ids.append(task_id)
        if task.execution_preview_id:
            state.task_execution_preview_ids[task_id] = task.execution_preview_id
        state.current_task_id = task_id
        state.status = "execution_preview_ready"
        self._states[autopilot_id] = state
        self._plans[autopilot_id] = plan
        return {"autopilot_id": autopilot_id, "task_id": task_id, "status": "execution_preview_ready", "message": "Execution preview prepared. No files were changed.", "plan_id": task.linked_plan_id, "execution_preview": preview, "task": task.model_dump(), "warnings": preview.get("warnings") or []}
