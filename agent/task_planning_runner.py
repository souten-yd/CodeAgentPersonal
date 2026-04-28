from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from agent.agent_prompts import PLAN_GENERATION_PROMPT, REQUIREMENT_ANALYSIS_PROMPT
from agent.clarification_manager import ClarificationManager
from agent.nexus_context_builder import NexusContextBuilder
from agent.plan_storage import PlanStorage
from agent.planner_phase1 import PlannerPhase1
from agent.requirement_analyzer import RequirementAnalyzer
from agent.requirement_schema import RequirementDefinition


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
        self.requirement_analyzer = RequirementAnalyzer(llm_json_fn=llm_json_fn)
        self.clarification_manager = ClarificationManager()
        self.nexus_builder = NexusContextBuilder(
            memory_search_fn=memory_search_fn,
            active_skills_fn=active_skills_fn,
            warning_logger=warning_logger,
            ca_data_dir=ca_data_dir,
        )

    def run(
        self,
        *,
        user_input: str,
        project_path: str,
        project_name: str = "",
        planning_mode: str = "standard",
        requirement_mode: str = "ask_when_needed",
        execution_mode: str = "plan_only",
        use_nexus: bool = True,
    ) -> dict:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        warnings: list[str] = []
        project_path = (project_path or "").strip()
        project_name = (project_name or "").strip()
        resolved_project_path = project_path

        repository_context = _build_repository_context(project_path)
        if repository_context.startswith("Project path not found:"):
            warnings.append("Project path was not found. Repository context fallback was used.")
        elif repository_context.startswith("Repository scan warning:"):
            warnings.append("Repository scan failed partially. Repository context fallback was used.")

        nexus_context = self.nexus_builder.build(
            user_input,
            use_nexus=use_nexus,
            project_path=project_path,
            project_name=project_name,
            resolved_project_path=resolved_project_path,
        )
        warnings.extend([str(x) for x in (nexus_context.get("warnings") or []) if str(x).strip()])

        requirement = self.requirement_analyzer.analyze(
            source_task_id=task_id,
            user_input=user_input,
            requirement_mode=requirement_mode,
            planning_mode=planning_mode,
            prompt=REQUIREMENT_ANALYSIS_PROMPT,
            nexus_context=nexus_context,
            repository_context=repository_context,
        )
        requirement.project_name = project_name
        requirement.project_path = project_path
        requirement.resolved_project_path = resolved_project_path
        warnings.extend(self.requirement_analyzer.get_last_warnings())

        clarification = self.clarification_manager.generate(requirement, requirement_mode, allow_derive=True)
        _req_json, req_md = self.storage.save_requirement(requirement)

        unresolved_required = self.clarification_manager.unresolved_required_questions(requirement)
        if unresolved_required:
            warnings = _dedup_warnings(warnings)
            return {
                "task_id": task_id,
                "requirement_id": requirement.requirement_id,
                "status": "waiting_for_clarification",
                "message": "Clarification required before planning.",
                "planning_mode": planning_mode if planning_mode in {"fast", "standard", "deep_nexus"} else "standard",
                "requirement_mode": requirement_mode,
                "execution_mode": execution_mode,
                "effective_execution_mode": "plan_only",
                "questions": [q.model_dump() for q in clarification.questions],
                "clarification": clarification.model_dump(),
                "requirement": requirement.model_dump(),
                "nexus_context": nexus_context,
                "repository_context": repository_context,
                "requirement_markdown_path": str(req_md),
                "warnings": warnings,
            }

        return self.continue_from_requirement(
            requirement_id=requirement.requirement_id,
            planning_mode=planning_mode,
            requirement_mode=requirement_mode,
            execution_mode=execution_mode,
            use_nexus=use_nexus,
            project_path=project_path,
            project_name=project_name,
            resolved_project_path=resolved_project_path,
            task_id=task_id,
            nexus_context=nexus_context,
            repository_context=repository_context,
            warnings=warnings,
        )

    def answer_requirement_questions(self, *, requirement_id: str, answers: list[dict]) -> dict:
        req_data = self.storage.load_requirement(requirement_id)
        requirement = RequirementDefinition(**req_data)
        requirement = self.clarification_manager.apply_answers(requirement, answers)
        self.storage.save_requirement(requirement)
        remaining = [q.model_dump() for q in requirement.open_questions]
        return {
            "requirement_id": requirement.requirement_id,
            "status": "answered" if not remaining else "waiting_for_clarification",
            "requirement": requirement.model_dump(),
            "remaining_questions": remaining,
        }

    def skip_requirement_questions(self, *, requirement_id: str) -> dict:
        req_data = self.storage.load_requirement(requirement_id)
        requirement = RequirementDefinition(**req_data)
        requirement = self.clarification_manager.skip_with_defaults(requirement)
        self.storage.save_requirement(requirement)
        return {
            "requirement_id": requirement.requirement_id,
            "status": "answered",
            "requirement": requirement.model_dump(),
            "remaining_questions": [],
        }

    def continue_from_requirement(
        self,
        *,
        requirement_id: str,
        planning_mode: str,
        requirement_mode: str,
        execution_mode: str,
        use_nexus: bool,
        project_path: str | None = None,
        project_name: str = "",
        resolved_project_path: str = "",
        task_id: str | None = None,
        nexus_context: dict | None = None,
        repository_context: str | None = None,
        warnings: list[str] | None = None,
    ) -> dict:
        req_data = self.storage.load_requirement(requirement_id)
        requirement = RequirementDefinition(**req_data)
        warnings = list(warnings or [])
        project_path = (project_path or "").strip()
        project_name = (project_name or "").strip()
        resolved_project_path = (resolved_project_path or "").strip()

        if not project_path:
            project_path = (requirement.resolved_project_path or requirement.project_path or "").strip()
        if not project_name:
            project_name = (requirement.project_name or "").strip()
        if not resolved_project_path:
            resolved_project_path = project_path
        requirement.project_name = project_name
        requirement.project_path = project_path
        requirement.resolved_project_path = resolved_project_path

        clarification = self.clarification_manager.generate(requirement, requirement_mode, allow_derive=False)
        unresolved_required = self.clarification_manager.unresolved_required_questions(requirement)
        self.storage.save_requirement(requirement)

        if nexus_context is None:
            nexus_context = self.nexus_builder.build(
                requirement.user_input,
                use_nexus=use_nexus,
                project_path=project_path,
                project_name=project_name,
                resolved_project_path=resolved_project_path,
            )
            warnings.extend([str(x) for x in (nexus_context.get("warnings") or []) if str(x).strip()])

        if unresolved_required:
            return {
                "task_id": task_id or requirement.source_task_id,
                "requirement_id": requirement.requirement_id,
                "status": "waiting_for_clarification",
                "message": "Clarification required before planning.",
                "planning_mode": planning_mode if planning_mode in {"fast", "standard", "deep_nexus"} else "standard",
                "requirement_mode": requirement_mode,
                "execution_mode": execution_mode,
                "effective_execution_mode": "plan_only",
                "questions": [q.model_dump() for q in clarification.questions],
                "clarification": clarification.model_dump(),
                "requirement": requirement.model_dump(),
                "nexus_context": nexus_context,
                "resolved_project_path": resolved_project_path,
                "warnings": _dedup_warnings(warnings),
            }

        if repository_context is None:
            repository_context = _build_repository_context(project_path or "")
            if repository_context.startswith("Project path not found:"):
                warnings.append("Project path was not found. Repository context fallback was used.")
            elif repository_context.startswith("Repository scan warning:"):
                warnings.append("Repository scan failed partially. Repository context fallback was used.")

        plan = self.planner.build_plan(
            requirement=requirement,
            planning_mode=planning_mode,
            prompt=PLAN_GENERATION_PROMPT,
            nexus_context=nexus_context,
            repository_context=repository_context,
        )
        warnings.extend(self.planner.get_last_warnings())

        _req_json, req_md = self.storage.save_requirement(requirement)
        _plan_json, plan_md = self.storage.save_plan(plan, user_input=requirement.user_input, interpreted_goal=requirement.interpreted_goal)
        warnings = _dedup_warnings(warnings)

        return {
            "task_id": task_id or requirement.source_task_id,
            "requirement_id": requirement.requirement_id,
            "plan_id": plan.plan_id,
            "status": "planned",
            "message": "Plan generated. No implementation was executed in Phase 2.",
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
            "resolved_project_path": resolved_project_path,
            "warnings": warnings,
        }


def _dedup_warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys([w.strip() for w in warnings if isinstance(w, str) and w.strip()]))
