from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from agent.agent_prompts import PLAN_GENERATION_PROMPT, REQUIREMENT_ANALYSIS_PROMPT
from agent.nexus_context_builder import NexusContextBuilder
from agent.plan_storage import PlanStorage
from agent.planner_phase1 import PlannerPhase1


def _build_repository_context(project_path: str, max_files: int = 30) -> str:
    root = Path(project_path).expanduser() if project_path else Path.cwd()
    if not root.exists() or not root.is_dir():
        return f"Project path not found: {root}"

    files: list[str] = []
    try:
        for path in root.rglob("*"):
            if len(files) >= max_files:
                break
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            s = str(rel)
            if any(part.startswith(".") for part in rel.parts):
                continue
            files.append(s)
    except Exception as exc:  # noqa: BLE001
        return f"Repository scan warning: {exc}"

    if not files:
        return "No visible files found."
    return "Top file candidates:\n" + "\n".join(f"- {f}" for f in files)


class TaskPlanningRunner:
    def __init__(
        self,
        *,
        ca_data_dir: str,
        llm_json_fn: Callable[[str, str], dict | None],
        memory_search_fn: Callable[[str, int], list] | None = None,
        active_skills_fn: Callable[[], list] | None = None,
        warning_logger: Callable[[str], None] | None = None,
    ) -> None:
        self.storage = PlanStorage(ca_data_dir)
        self.planner = PlannerPhase1(llm_json_fn=llm_json_fn)
        self.nexus_builder = NexusContextBuilder(
            memory_search_fn=memory_search_fn,
            active_skills_fn=active_skills_fn,
            warning_logger=warning_logger,
        )

    def run(
        self,
        *,
        user_input: str,
        project_path: str,
        planning_mode: str = "standard",
        requirement_mode: str = "ask_when_needed",
        execution_mode: str = "plan_only",
        use_nexus: bool = True,
    ) -> dict:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        repository_context = _build_repository_context(project_path)
        nexus_context = self.nexus_builder.build(user_input, use_nexus=use_nexus)

        requirement = self.planner.build_requirement(
            source_task_id=task_id,
            user_input=user_input,
            prompt=REQUIREMENT_ANALYSIS_PROMPT,
        )

        plan = self.planner.build_plan(
            requirement=requirement,
            planning_mode=planning_mode,
            prompt=PLAN_GENERATION_PROMPT,
            nexus_context=nexus_context,
            repository_context=repository_context,
        )

        _req_json, req_md = self.storage.save_requirement(requirement)
        _plan_json, plan_md = self.storage.save_plan(plan, user_input=user_input, interpreted_goal=requirement.interpreted_goal)

        return {
            "task_id": task_id,
            "requirement_id": requirement.requirement_id,
            "plan_id": plan.plan_id,
            "status": "planned",
            "message": "Plan generated. No implementation was executed in Phase 1.",
            "planning_mode": planning_mode if planning_mode in {"fast", "standard", "deep_nexus"} else "standard",
            "requirement_mode": requirement_mode,
            "execution_mode": execution_mode,
            "effective_execution_mode": "plan_only",
            "requirement": requirement.model_dump(),
            "plan": plan.model_dump(),
            "nexus_context": nexus_context,
            "repository_context": repository_context,
            "requirement_markdown_path": str(req_md),
            "plan_markdown_path": str(plan_md),
        }
