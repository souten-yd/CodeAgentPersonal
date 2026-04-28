from __future__ import annotations

import uuid
from typing import Callable

from agent.plan_schema import ImplementationStep, Plan
from agent.requirement_schema import RequirementCategoryScores, RequirementDefinition


class PlannerPhase1:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None]) -> None:
        self.llm_json_fn = llm_json_fn

    def build_requirement(
        self,
        *,
        source_task_id: str,
        user_input: str,
        prompt: str,
    ) -> RequirementDefinition:
        payload = self.llm_json_fn(prompt, user_input) or {}
        requirement_id = f"req_{uuid.uuid4().hex[:12]}"
        category_scores = payload.get("category_scores") or {}
        req = RequirementDefinition(
            requirement_id=requirement_id,
            source_task_id=source_task_id,
            user_input=user_input,
            interpreted_goal=str(payload.get("interpreted_goal", user_input[:120])),
            user_intent=str(payload.get("user_intent", "Solve user request safely and incrementally.")),
            task_type=str(payload.get("task_type", "other")),
            scope=_as_str_list(payload.get("scope")),
            out_of_scope=_as_str_list(payload.get("out_of_scope")),
            functional_requirements=_as_str_list(payload.get("functional_requirements")),
            non_functional_requirements=_as_str_list(payload.get("non_functional_requirements")),
            constraints=_as_str_list(payload.get("constraints")),
            assumptions=_as_str_list(payload.get("assumptions")),
            open_questions=_as_str_list(payload.get("open_questions")),
            answered_questions=payload.get("answered_questions") if isinstance(payload.get("answered_questions"), list) else [],
            requirement_completeness_score=float(payload.get("requirement_completeness_score", 0.65) or 0.65),
            category_scores=RequirementCategoryScores(
                goal=float(category_scores.get("goal", 0.7) or 0.7),
                scope=float(category_scores.get("scope", 0.6) or 0.6),
                functional_requirements=float(category_scores.get("functional_requirements", 0.7) or 0.7),
                non_functional_requirements=float(category_scores.get("non_functional_requirements", 0.6) or 0.6),
                constraints=float(category_scores.get("constraints", 0.6) or 0.6),
                done_definition=float(category_scores.get("done_definition", 0.65) or 0.65),
            ),
            priority=str(payload.get("priority", "medium")),
            done_definition=_as_str_list(payload.get("done_definition")),
            risks=_as_str_list(payload.get("risks")),
            user_confirmed=False,
            ready_for_planning=True,
        )
        if not req.functional_requirements:
            req.functional_requirements = ["ユーザー入力に沿った実装計画を作成する"]
        if not req.done_definition:
            req.done_definition = ["実装前の計画が合意可能な品質で提示されること"]
        return req

    def build_plan(
        self,
        *,
        requirement: RequirementDefinition,
        planning_mode: str,
        prompt: str,
        nexus_context: dict,
        repository_context: str,
    ) -> Plan:
        planner_input = "\n\n".join([
            f"User Input:\n{requirement.user_input}",
            f"Requirement Summary:\nGoal={requirement.interpreted_goal}\nFunctional={requirement.functional_requirements}\nNonFunctional={requirement.non_functional_requirements}\nConstraints={requirement.constraints}",
            f"Nexus Context:\n{nexus_context}",
            f"Repository Context:\n{repository_context}",
            f"Planning Mode: {planning_mode or 'standard'}",
        ])
        payload = self.llm_json_fn(prompt, planner_input) or {}
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        raw_steps = payload.get("implementation_steps") if isinstance(payload.get("implementation_steps"), list) else []
        steps: list[ImplementationStep] = []
        for i, item in enumerate(raw_steps[:20], start=1):
            if not isinstance(item, dict):
                continue
            steps.append(
                ImplementationStep(
                    step_id=f"step_{i}",
                    title=str(item.get("title", f"Step {i}")),
                    description=str(item.get("description", "")),
                    target_files=_as_str_list(item.get("target_files")),
                    action_type=_safe_action_type(str(item.get("action_type", "inspect"))),
                    risk_level=_safe_risk_level(str(item.get("risk_level", "low"))),
                    verification=str(item.get("verification", "")),
                    rollback=str(item.get("rollback", "")),
                )
            )
        if not steps:
            steps = [
                ImplementationStep(
                    step_id="step_1",
                    title="現状調査と変更方針の確定",
                    description="関連ファイルと既存API/UIフローを確認し、変更範囲を確定する。",
                    target_files=[],
                    action_type="inspect",
                    risk_level="low",
                    verification="対象の既存機能が把握できていること",
                    rollback="変更未実施のため不要",
                )
            ]

        selected_arch = str(payload.get("selected_architecture", "Incremental additive changes"))
        mode = planning_mode if planning_mode in {"fast", "standard", "deep_nexus"} else "standard"
        plan = Plan(
            plan_id=plan_id,
            requirement_id=requirement.requirement_id,
            mode=mode,
            task_type=requirement.task_type if requirement.task_type in {"bugfix", "feature", "refactor", "ui", "project_generation", "investigation", "other"} else "other",
            user_goal=str(payload.get("user_goal", requirement.interpreted_goal)),
            requirement_summary=str(payload.get("requirement_summary", requirement.interpreted_goal)),
            nexus_context_summary=str(payload.get("nexus_context_summary", nexus_context.get("summary", ""))),
            repository_context=repository_context,
            assumptions=_as_str_list(payload.get("assumptions")) or requirement.assumptions,
            constraints=_as_str_list(payload.get("constraints")) or requirement.constraints,
            architecture_options=_as_str_list(payload.get("architecture_options")) or [selected_arch],
            selected_architecture=selected_arch,
            rejected_architectures=_as_str_list(payload.get("rejected_architectures")),
            implementation_steps=steps,
            target_files=_as_str_list(payload.get("target_files")),
            expected_file_changes=_as_str_list(payload.get("expected_file_changes")),
            risks=_as_str_list(payload.get("risks")) or requirement.risks,
            test_plan=_as_str_list(payload.get("test_plan")),
            verification_plan=_as_str_list(payload.get("verification_plan")),
            rollback_plan=_as_str_list(payload.get("rollback_plan")),
            done_definition=_as_str_list(payload.get("done_definition")) or requirement.done_definition,
            destructive_change_detected=bool(payload.get("destructive_change_detected", False)),
            requires_user_confirmation=bool(payload.get("requires_user_confirmation", False)),
            status="planned",
        )
        if not plan.test_plan:
            plan.test_plan = ["APIレスポンス構造の確認", "保存ファイル(JSON/Markdown)の存在確認"]
        if not plan.rollback_plan:
            plan.rollback_plan = ["追加ファイルを削除し、変更をrevertする"]
        return plan


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_action_type(value: str) -> str:
    allowed = {"create", "update", "delete", "inspect", "run_command", "test"}
    return value if value in allowed else "inspect"


def _safe_risk_level(value: str) -> str:
    allowed = {"low", "medium", "high"}
    return value if value in allowed else "low"
