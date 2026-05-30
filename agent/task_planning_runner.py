from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from agent.adversarial_plan_critic import AdversarialPlanCritic
from agent.agent_prompts import DEEP_PLAN_GENERATION_PROMPT, PLAN_GENERATION_PROMPT, REQUIREMENT_ANALYSIS_PROMPT
from agent.clarification_manager import ClarificationManager
from agent.deep_planner import DeepPlanner
from agent.clarification_policy import ClarificationPolicy
from agent.nexus_context_builder import NexusContextBuilder
from agent.plan_reviewer import PlanReviewer
from agent.research_conductor import ResearchConductor
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
        self.deep_planner = DeepPlanner(llm_json_fn=llm_json_fn)
        self.requirement_analyzer = RequirementAnalyzer(llm_json_fn=llm_json_fn)
        self.plan_reviewer = PlanReviewer()
        self.research_conductor = ResearchConductor(llm_json_fn=llm_json_fn)
        self.adversarial_critic = AdversarialPlanCritic(llm_json_fn=llm_json_fn)
        self.clarification_manager = ClarificationManager()
        self.clarification_policy = ClarificationPolicy()
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

        decision = self.clarification_policy.classify(
            user_input=user_input,
            task_type=requirement.task_type,
            requirement_mode=requirement_mode,
            project_context=f"{project_name} {project_path}",
        )
        unresolved_required = self.clarification_manager.unresolved_required_questions(requirement)
        if decision.decision == "required" and unresolved_required:
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
                "clarification_policy": {"decision": decision.decision, "reason": decision.reason},
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
        decision = self.clarification_policy.classify(
            user_input=requirement.user_input,
            task_type=requirement.task_type,
            requirement_mode=requirement_mode,
            project_context=f"{project_name} {project_path}",
        )
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

        if decision.decision == "required" and unresolved_required:
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
                "clarification_policy": {"decision": decision.decision, "reason": decision.reason},
                "warnings": _dedup_warnings(warnings),
            }

        if repository_context is None:
            repository_context = _build_repository_context(project_path or "")
            if repository_context.startswith("Project path not found:"):
                warnings.append("Project path was not found. Repository context fallback was used.")
            elif repository_context.startswith("Repository scan warning:"):
                warnings.append("Repository scan failed partially. Repository context fallback was used.")

        # Research-first: survey the codebase before planning so the planner works from grounded
        # evidence (Claude Code's "explore before you plan"). Findings are injected into the planner's
        # repository_context as a Research Evidence section. Degrades to empty when no LLM.
        nexus_text_for_research = ""
        if isinstance(nexus_context, dict):
            nexus_text_for_research = str(nexus_context.get("compact_text") or nexus_context.get("summary") or "")
        research_findings = self.research_conductor.conduct(
            user_input=requirement.user_input,
            interpreted_goal=requirement.interpreted_goal,
            repository_context=repository_context,
            nexus_text=nexus_text_for_research,
        )
        warnings.extend(research_findings.warnings)
        research_text = research_findings.to_prompt_text()
        if research_text:
            repository_context = f"{repository_context}\n\n=== Research Evidence ===\n{research_text}"

        if planning_mode == "deep_nexus":
            plan = self.planner.build_plan(
                requirement=requirement,
                planning_mode=planning_mode,
                prompt=PLAN_GENERATION_PROMPT,
                nexus_context=nexus_context,
                repository_context=repository_context,
            )
            deep_plan = self.deep_planner.build_deep_plan(
                requirement=requirement,
                prompt=DEEP_PLAN_GENERATION_PROMPT,
                nexus_context=nexus_context,
                repository_context=repository_context,
            )
            plan.deep_planning = deep_plan.model_dump()
            plan.architecture_options = [f"[{o.option_id}] {o.title}: {o.summary}" for o in deep_plan.architecture_options]
            selected = next((o for o in deep_plan.architecture_options if o.option_id == deep_plan.selected_option_id), None)
            plan.selected_architecture = f"[{deep_plan.selected_option_id}] {selected.title}" if selected else deep_plan.selected_option_id
            plan.rejected_architectures = [
                f"[{o.option_id}] {o.title}: {o.why_rejected}" for o in deep_plan.architecture_options if o.option_id != deep_plan.selected_option_id
            ]
            warnings.extend(self.deep_planner.get_last_warnings())
            warnings.extend(self.planner.get_last_warnings())
        else:
            plan = self.planner.build_plan(
                requirement=requirement,
                planning_mode=planning_mode,
                prompt=PLAN_GENERATION_PROMPT,
                nexus_context=nexus_context,
                repository_context=repository_context,
            )
            warnings.extend(self.planner.get_last_warnings())

        # Adversarial critique: attack the plan from multiple angles before any code is written. If a
        # high/critical gap is found, regenerate the plan ONCE with the critique appended, then re-critique
        # for the record. Complements (does not replace) the rule-based PlanReviewer below.
        critique = self.adversarial_critic.critique(
            plan_summary=self._plan_summary(plan),
            requirement_summary=self._requirement_summary(requirement),
        )
        warnings.extend(critique.warnings)
        if critique.requires_revision and planning_mode != "deep_nexus":
            revision_context = f"{repository_context}\n\n=== Adversarial Critique (fix high/critical gaps) ===\n{self._critique_text(critique)}"
            revised = self.planner.build_plan(
                requirement=requirement,
                planning_mode=planning_mode,
                prompt=PLAN_GENERATION_PROMPT,
                nexus_context=nexus_context,
                repository_context=revision_context,
            )
            warnings.extend(self.planner.get_last_warnings())
            if revised.implementation_steps:
                plan = revised
                warnings.append("plan_revised_after_adversarial_critique")
                critique = self.adversarial_critic.critique(
                    plan_summary=self._plan_summary(plan),
                    requirement_summary=self._requirement_summary(requirement),
                )
                warnings.extend(critique.warnings)

        review_result = self.plan_reviewer.review(
            requirement=requirement,
            plan=plan,
            nexus_context=nexus_context if isinstance(nexus_context, dict) else {},
            repository_context=repository_context,
        )
        self._merge_critique_into_review(review_result, critique)
        plan.destructive_change_detected = bool(review_result.destructive_change_detected)
        plan.requires_user_confirmation = bool(review_result.requires_user_confirmation)
        if review_result.overall_risk == "critical":
            plan.status = "rejected" if review_result.recommended_next_action == "reject_plan" else "needs_revision"
        elif review_result.requires_user_confirmation:
            plan.status = "needs_confirmation"
        else:
            plan.status = "planned"

        _req_json, req_md = self.storage.save_requirement(requirement)
        _plan_json, plan_md = self.storage.save_plan(
            plan,
            user_input=requirement.user_input,
            interpreted_goal=requirement.interpreted_goal,
            review_result=review_result,
        )
        _review_json, _review_md = self.storage.save_review(review_result)

        warnings.extend([str(x) for x in (review_result.warnings or []) if str(x).strip()])
        warnings = _dedup_warnings(warnings)

        message = "Plan generated. No implementation was executed in Phase 4."
        if plan.status == "needs_confirmation":
            message = "Plan requires user confirmation before execution."
        elif plan.status in {"needs_revision", "rejected"}:
            message = "Plan review detected critical issues. Revision is required before execution."

        return {
            "task_id": task_id or requirement.source_task_id,
            "requirement_id": requirement.requirement_id,
            "plan_id": plan.plan_id,
            "status": plan.status,
            "message": message,
            "planning_mode": planning_mode if planning_mode in {"fast", "standard", "deep_nexus"} else "standard",
            "requirement_mode": requirement_mode,
            "execution_mode": execution_mode,
            "effective_execution_mode": "plan_only",
            "requirement": requirement.model_dump(),
            "plan": plan.model_dump(),
            "review_result": review_result.model_dump(),
            "research_findings": research_findings.model_dump(),
            "adversarial_critique": critique.model_dump(),
            "nexus_context": nexus_context,
            "repository_context": repository_context,
            "requirement_markdown_path": str(req_md),
            "plan_markdown_path": str(plan_md),
            "resolved_project_path": resolved_project_path,
            "warnings": warnings,
        }

    def _plan_summary(self, plan) -> dict:
        steps = [
            {
                "title": getattr(s, "title", ""),
                "description": getattr(s, "description", "")[:300],
                "target_files": list(getattr(s, "target_files", []) or []),
                "action_type": getattr(s, "action_type", ""),
                "risk_level": getattr(s, "risk_level", ""),
            }
            for s in (getattr(plan, "implementation_steps", []) or [])[:20]
        ]
        return {
            "user_goal": getattr(plan, "user_goal", ""),
            "selected_architecture": getattr(plan, "selected_architecture", ""),
            "implementation_steps": steps,
            "test_plan": list(getattr(plan, "test_plan", []) or []),
            "risks": list(getattr(plan, "risks", []) or []),
        }

    def _requirement_summary(self, requirement) -> dict:
        return {
            "interpreted_goal": getattr(requirement, "interpreted_goal", ""),
            "functional_requirements": list(getattr(requirement, "functional_requirements", []) or []),
            "out_of_scope": list(getattr(requirement, "out_of_scope", []) or []),
            "done_definition": list(getattr(requirement, "done_definition", []) or []),
        }

    def _critique_text(self, critique) -> str:
        lines: list[str] = []
        for f in critique.findings:
            if f.severity in {"high", "critical"}:
                lines.append(f"- [{f.severity}/{f.angle}] {f.title}: {f.detail} -> {f.recommendation}")
        return "\n".join(lines)[:4000]

    def _merge_critique_into_review(self, review_result, critique) -> None:
        # Surface LLM critique findings on the rule-based review so downstream consumers see one record.
        from agent.plan_review_schema import PlanReviewFinding

        rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        for i, f in enumerate(critique.findings):
            sev = f.severity if f.severity in {"info", "warning", "high", "critical"} else "info"
            review_result.findings.append(PlanReviewFinding(
                finding_id=f"adversarial_{i+1}",
                severity=sev,
                category="other",
                title=f.title or f"{f.angle} critique",
                detail=f.detail,
                recommendation=f.recommendation,
            ))
            if sev in {"high", "critical"}:
                review_result.blocking_findings.append(f"adversarial_{i+1}")
        # Escalate overall risk if the critique found something worse than the rule-based review.
        if rank.get(critique.consensus_risk, 0) > rank.get(review_result.overall_risk, 0):
            review_result.overall_risk = critique.consensus_risk
        if critique.requires_revision:
            review_result.warnings.append("adversarial_critique_flagged_high_risk")


def _dedup_warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys([w.strip() for w in warnings if isinstance(w, str) and w.strip()]))
