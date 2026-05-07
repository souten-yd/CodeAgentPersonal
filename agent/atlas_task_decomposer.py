from __future__ import annotations

from typing import Callable

from agent.atlas_autopilot_schema import AtlasAutopilotTask
from agent.deep_planner_schema import DeepPlanPayload


class AtlasTaskDecomposer:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None] | None = None):
        self.llm_json_fn = llm_json_fn

    def decompose(
        self,
        *,
        autopilot_id: str,
        user_goal: str,
        deep_plan: DeepPlanPayload | None,
        project_path: str = "",
        project_name: str = "",
    ) -> list[AtlasAutopilotTask]:
        if deep_plan is None:
            return self._fallback_tasks(user_goal=user_goal)

        selected = next((o for o in deep_plan.architecture_options if o.option_id == deep_plan.selected_option_id), None)
        acceptance = [*deep_plan.verification_strategy, *deep_plan.done_definition]
        phases = [p for p in deep_plan.implementation_phases if str(p).strip()] or [
            "Requirement refinement",
            "Implementation plan preparation",
            "Verification strategy preparation",
        ]
        phases = phases[:7]
        tasks: list[AtlasAutopilotTask] = []
        for idx, phase in enumerate(phases, start=1):
            task_id = f"{autopilot_id}_task_{idx}"
            tasks.append(
                AtlasAutopilotTask(
                    task_id=task_id,
                    title=_title_from_phase(phase, idx),
                    description=phase,
                    goal=f"{deep_plan.user_goal or user_goal} の実行に向けて {phase} を具体化する",
                    rationale=(selected.summary if selected else "Deep plan selected optionに沿って段階的に分解する"),
                    expected_output=f"{phase} の成果物（Atlas Coreへ渡せるタスク定義）",
                    task_type="planning",
                    priority="high" if idx <= 2 else "medium",
                    depends_on=[] if idx == 1 else [f"{autopilot_id}_task_{idx-1}"],
                    suggested_planning_mode="deep_nexus" if idx >= 2 else "standard",
                    suggested_requirement_mode="ask_when_needed",
                    risk_level=(selected.risk_level if selected else "medium"),
                    estimated_complexity=(selected.estimated_complexity if selected else "medium"),
                    target_areas=(selected.target_files if selected else [project_name or project_path or "repository"]),
                    acceptance_criteria=acceptance[:4] if acceptance else ["Atlas preview-only safety constraints are preserved."],
                )
            )

        if len(tasks) < 3:
            tasks.extend(self._fallback_tasks(user_goal=user_goal, start_index=len(tasks) + 1, autopilot_id=autopilot_id))
        return tasks

    def _fallback_tasks(self, *, user_goal: str, start_index: int = 1, autopilot_id: str = "fallback") -> list[AtlasAutopilotTask]:
        titles = ["Requirement refinement", "Architecture and touchpoint planning", "Final review and handoff"]
        out: list[AtlasAutopilotTask] = []
        for i, t in enumerate(titles, start=start_index):
            out.append(
                AtlasAutopilotTask(
                    task_id=f"{autopilot_id}_task_{i}",
                    title=t,
                    description=f"Preview-only decomposition task: {t}",
                    goal=user_goal or "Clarify goal and planning boundaries",
                    rationale="Fallback decomposition when deep planning details are unavailable.",
                    expected_output="Atlas task candidate with constraints and dependencies.",
                    task_type="planning",
                    depends_on=[] if i == start_index else [f"{autopilot_id}_task_{i-1}"],
                    acceptance_criteria=["No file changes.", "Execution stays disabled in preview-only mode."],
                )
            )
        return out


def _title_from_phase(phase: str, index: int) -> str:
    cleaned = (phase or "").strip()
    if not cleaned:
        return f"Task {index}"
    return cleaned.split(":", 1)[-1].strip() if ":" in cleaned else cleaned
