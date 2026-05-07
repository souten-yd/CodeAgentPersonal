from __future__ import annotations

import uuid

from agent.atlas_autopilot_schema import (
    AtlasAutopilotPlan,
    AtlasAutopilotRequest,
    AtlasAutopilotRunState,
    AtlasAutopilotTask,
)


class AtlasAutopilot:
    """Preview-only orchestrator skeleton for Atlas Autopilot.

    This class intentionally avoids direct file edits and destructive actions.
    """

    def __init__(self, *, ca_data_dir: str = "", planning_runner=None) -> None:
        self.ca_data_dir = ca_data_dir
        self.planning_runner = planning_runner
        self._states: dict[str, AtlasAutopilotRunState] = {}

    def create_autopilot_plan(self, request: AtlasAutopilotRequest) -> dict:
        goal = (request.user_goal or "").strip()
        task_title = goal if goal else "Clarify Atlas Autopilot goal"
        tasks = [
            AtlasAutopilotTask(
                task_id=f"auto_task_{uuid.uuid4().hex[:8]}",
                title="Interpret user goal",
                description=f"Translate user intent into Atlas-safe planning scope: {task_title}",
                task_type="planning",
                priority="high",
            ),
            AtlasAutopilotTask(
                task_id=f"auto_task_{uuid.uuid4().hex[:8]}",
                title="Prepare guided Atlas plan preview",
                description="Create preview-only task decomposition for Plan → Review → Approval → Execute Preview → Patch Review → Verification.",
                task_type="preview",
                priority="high",
                depends_on=[],
            ),
        ]
        plan = AtlasAutopilotPlan(
            autopilot_id=request.autopilot_id,
            user_goal=request.user_goal,
            interpreted_goal=f"Atlas Autopilot preview plan for: {task_title}",
            tasks=tasks,
            assumptions=[
                "Preview-only mode is active; no file edits are executed.",
                "Existing Atlas guided workflow remains the source of truth.",
            ],
            risks=[
                "Large goals may require clarification before detailed planning.",
                "Execution details are intentionally deferred to later PRs.",
            ],
            safety_constraints=[
                "No direct file edits by Agent runtime.",
                "All modifications must pass Atlas Plan → Review → Approval → Executor → Patch Review → Verification.",
                "No auto-approve, auto-apply, or destructive commands.",
            ],
            done_definition=[
                "Autopilot preview generated with at least one task.",
                "Atlas safety pipeline constraints are explicit.",
            ],
        )
        self._states[request.autopilot_id] = AtlasAutopilotRunState(
            autopilot_id=request.autopilot_id,
            status="planned",
            summary="Preview plan created. No execution was performed.",
        )
        return plan.model_dump()

    def start_preview(self, request: AtlasAutopilotRequest) -> dict:
        plan = self.create_autopilot_plan(request)
        state = AtlasAutopilotRunState(
            autopilot_id=request.autopilot_id,
            status="preview_ready",
            blocked_task_ids=["destructive_actions_not_supported_in_preview"],
            warnings=["Preview only: execution is disabled in this PR."],
            summary="Atlas Autopilot preview generated. No files were changed.",
        )
        # TODO: for larger goals, create_autopilot_plan should call DeepPlanner (deep_nexus) before execution stages.
        # TODO: task decomposition should consume DeepPlanPayload architecture options in a follow-up PR.
        # TODO: keep this PR preview-only; no implementation execution wiring here.
        self._states[request.autopilot_id] = state
        return {
            "autopilot_id": request.autopilot_id,
            "status": state.status,
            "message": state.summary,
            "autopilot_plan": plan,
            "tasks": plan.get("tasks", []),
            "warnings": state.warnings,
        }

    def get_state(self, autopilot_id: str) -> dict:
        state = self._states.get(autopilot_id)
        if state is None:
            state = AtlasAutopilotRunState(
                autopilot_id=autopilot_id,
                status="draft",
                summary="No state found. Preview has not started.",
            )
        # Future: persist/load from ca_data/autopilot_runs/
        return state.model_dump()
