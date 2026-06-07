from __future__ import annotations

import re
import uuid
from typing import Callable

from agent.atlas_llm_output_models import PlanGenerationOutput
from agent.atlas_llm_schemas import plan_generation_json_schema
from agent.atlas_structured_output import generate_structured
from agent.plan_schema import ImplementationStep, Plan
from agent.requirement_schema import RequirementCategoryScores, RequirementDefinition

_HIGH_RISK_EN = (
    "delete",
    "remove",
    "rm",
    "run_command",
    "shell",
    "execute",
    "credential",
    "secret",
    "password",
    "token",
    "database",
    "migration",
    "production",
)
_HIGH_RISK_JA = ("削除", "破壊", "実行", "本番")
_ADVISORY_NOISE = (
    "advisory repository context",
    "do not execute",
    "don't execute",
    "do not run",
    "エージェントは実行しない",
)
_CREATE_INTENT_EN = ("create", "make", "build", "generate", "add", "write")
_CREATE_INTENT_JA = ("作って", "作成", "生成", "追加", "実装")
_HTML_HINTS = ("html", "web page", "webpage", "browser", "ページ", "画面", "虹色", "ぼかし", "hello world")

class PlannerPhase1:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None]) -> None:
        self.llm_json_fn = llm_json_fn
        self._last_warnings: list[str] = []

    def get_last_warnings(self) -> list[str]:
        return list(self._last_warnings)

    def build_requirement(
        self,
        *,
        source_task_id: str,
        user_input: str,
        prompt: str,
    ) -> RequirementDefinition:
        warnings: list[str] = []
        raw_payload = self.llm_json_fn(prompt, user_input)
        analysis_failed = False
        if raw_payload is None:
            analysis_failed = True
            warnings.append("Requirement analysis LLM output could not be parsed. Fallback requirement was generated.")
            payload: dict = {}
        elif not isinstance(raw_payload, dict):
            analysis_failed = True
            warnings.append("Requirement analysis LLM output was not a JSON object. Fallback requirement was generated.")
            payload = {}
        else:
            payload = raw_payload
            if not payload:
                analysis_failed = True
                warnings.append("Requirement analysis LLM output was empty. Fallback requirement was generated.")
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
            acceptance_criteria=_as_str_list(payload.get("acceptance_criteria")),
            verification_contract=payload.get("verification_contract") if isinstance(payload.get("verification_contract"), dict) else {},
            expected_changes=_as_str_list(payload.get("expected_changes")),
            preserve_behaviors=_as_str_list(payload.get("preserve_behaviors")),
            selected_architecture=str(payload.get("selected_architecture") or ""),
            requirement_items=_as_requirement_items(payload.get("requirements") or payload.get("requirement_items")),
            risks=_as_str_list(payload.get("risks")),
            user_confirmed=False,
            ready_for_planning=not analysis_failed,
            analysis_status="failed" if analysis_failed else "ok",
        )
        if not req.functional_requirements:
            if not analysis_failed:
                req.functional_requirements = ["ユーザー入力に沿った実装計画を作成する"]
                warnings.append("Requirement payload did not include functional_requirements. Fallback requirement item was generated.")
            else:
                warnings.append("Requirement analysis failed; functional_requirements were left empty.")
        if not req.done_definition:
            if not analysis_failed:
                req.done_definition = ["実装前の計画が合意可能な品質で提示されること"]
                warnings.append("Requirement payload did not include done_definition. Fallback done_definition was generated.")
            else:
                warnings.append("Requirement analysis failed; done_definition was left empty.")
        if analysis_failed:
            req.ready_for_planning = False
        self._last_warnings = warnings
        req.analysis_warnings = list(warnings)
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
        warnings: list[str] = []
        nexus_text = _format_nexus_context(nexus_context)
        planner_input = "\n\n".join([
            f"User Input:\n{requirement.user_input}",
            f"Requirement Summary:\nGoal={requirement.interpreted_goal}\nFunctional={requirement.functional_requirements}\nNonFunctional={requirement.non_functional_requirements}\nConstraints={requirement.constraints}",
            f"Nexus Context:\n{nexus_text}",
            f"Repository Context:\n{repository_context}",
            f"Planning Mode: {planning_mode or 'standard'}",
        ])
        structured = generate_structured(
            self.llm_json_fn,
            prompt,
            planner_input,
            json_schema=plan_generation_json_schema(),
            model=PlanGenerationOutput,
        )
        raw_payload = structured.data
        warnings.extend(structured.warnings)
        fallback_reason = ""
        fallback_raw_tail = ""
        if raw_payload is None:
            fallback_reason = "parse_error"
            warnings.append("Plan generation LLM output could not be parsed. Fallback plan was generated.")
            payload: dict = {}
        elif not isinstance(raw_payload, dict):
            fallback_reason = "not_object"
            fallback_raw_tail = str(raw_payload)[-500:]
            warnings.append("Plan generation LLM output was not a JSON object. Fallback plan was generated.")
            payload = {}
        else:
            payload = raw_payload
            if not payload:
                fallback_reason = "empty"
                warnings.append("Plan generation LLM output was empty. Fallback plan was generated.")
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
                    goal=str(item.get("goal") or item.get("description", "")),
                    requirement_ids=_as_str_list(item.get("requirement_ids") or item.get("linked_requirement_ids")),
                    acceptance_criteria=_as_str_list(item.get("acceptance_criteria")),
                    target_files=_as_str_list(item.get("target_files")),
                    expected_changes=_as_str_list(item.get("expected_changes") or item.get("changes")),
                    action_type=_safe_action_type(str(item.get("action_type", "inspect"))),
                    risk_level=_safe_risk_level(str(item.get("risk_level", "low"))),
                    verification=str(item.get("verification", "")),
                    verification_contract=item.get("verification_contract") if isinstance(item.get("verification_contract"), dict) else {},
                    rollback=str(item.get("rollback", "")),
                    preserve_behaviors=_as_str_list(item.get("preserve_behaviors")),
                )
            )
        if not steps:
            # The model returned a parseable payload but no usable steps. Record it as the fallback
            # reason so the no-steps case (which otherwise strands patch generation at 0/N) stays
            # visible in plan.metadata, matching parse_error/not_object/empty above.
            if not fallback_reason:
                fallback_reason = "no_implementation_steps"
                fallback_raw_tail = str(raw_payload)[-500:]
            fallback_target = _infer_simple_fallback_target(requirement.user_input)
            warnings.append("Plan generation LLM output did not include implementation_steps. Fallback plan was generated.")
            if fallback_target:
                steps = [
                    ImplementationStep(
                        step_id="step_1",
                        title=f"実装スケルトンを作成する ({fallback_target})",
                        description=f"ユーザー要件に沿って {fallback_target} を作成し、最小の動作確認ができる実装スケルトンを用意する。",
                        goal=f"ユーザー要件に沿って {fallback_target} の実装スケルトンを用意する。",
                        acceptance_criteria=[f"{fallback_target} が作成され、要求された表示内容の土台が含まれること"],
                        target_files=[fallback_target],
                        action_type="create",
                        risk_level="low",
                        verification=f"{fallback_target} が作成され、要求された表示内容の土台が含まれること",
                        rollback=f"{fallback_target} を削除する",
                    )
                ]
                warnings.append("planner_fallback_skeleton_generated")
            else:
                steps = [
                    ImplementationStep(
                        step_id="step_1",
                        title="現状調査と変更方針の確定",
                        description="関連ファイルと既存API/UIフローを確認し、変更範囲を確定する。",
                        goal="関連ファイルと既存フローを確認し、実装前に変更範囲を確定する。",
                        acceptance_criteria=["対象の既存機能と変更範囲が把握できていること"],
                        target_files=[],
                        action_type="inspect",
                        risk_level="low",
                        verification="対象の既存機能が把握できていること",
                        rollback="変更未実施のため不要",
                    )
                ]
                warnings.append("Fallback inspection step was generated.")

        selected_arch = str(payload.get("selected_architecture", "Incremental additive changes"))
        mode = planning_mode if planning_mode in {"fast", "standard", "deep_nexus"} else "standard"
        plan = Plan(
            plan_id=plan_id,
            requirement_id=requirement.requirement_id,
            mode=mode,
            task_type=requirement.task_type if requirement.task_type in {"bugfix", "feature", "refactor", "ui", "project_generation", "investigation", "other"} else "other",
            original_user_request=requirement.user_input,
            user_goal=str(payload.get("user_goal", requirement.interpreted_goal)),
            requirement_summary=str(payload.get("requirement_summary", requirement.interpreted_goal)),
            requirements=_as_requirement_items(payload.get("requirements") or requirement.requirement_items),
            nexus_context_summary=str(payload.get("nexus_context_summary", nexus_context.get("summary", ""))),
            repository_context=repository_context,
            assumptions=_as_str_list(payload.get("assumptions")) or requirement.assumptions,
            constraints=_as_str_list(payload.get("constraints")) or requirement.constraints,
            architecture_options=_as_str_list(payload.get("architecture_options")) or [selected_arch],
            selected_architecture=selected_arch,
            preserve_behaviors=_as_str_list(payload.get("preserve_behaviors")) or requirement.preserve_behaviors,
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
            metadata={"planner_fallback": {"reason": fallback_reason, "raw_output_tail": fallback_raw_tail}} if fallback_reason else {},
        )
        if not plan.test_plan:
            plan.test_plan = ["APIレスポンス構造の確認", "保存ファイル(JSON/Markdown)の存在確認"]
            warnings.append("Plan payload did not include test_plan. Fallback test plan was generated.")
        if not plan.rollback_plan:
            plan.rollback_plan = ["追加ファイルを削除し、変更をrevertする"]
            warnings.append("Plan payload did not include rollback_plan. Fallback rollback plan was generated.")
        self._last_warnings = warnings
        return plan


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_requirement_items(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            req = dict(item)
            description = str(req.get("description") or req.get("title") or req.get("goal") or "").strip()
            if not description:
                continue
            req.setdefault("requirement_id", str(req.get("id") or f"req_{index:03d}"))
            req["description"] = description
            req.setdefault("required", True)
            out.append(req)
        elif str(item).strip():
            out.append({"requirement_id": f"req_{index:03d}", "description": str(item).strip(), "required": True})
    return out


def _safe_action_type(value: str) -> str:
    allowed = {"create", "update", "delete", "inspect", "run_command", "test"}
    return value if value in allowed else "inspect"


def _safe_risk_level(value: str) -> str:
    allowed = {"low", "medium", "high"}
    return value if value in allowed else "low"


def _format_nexus_context(nexus_context: dict) -> str:
    if not isinstance(nexus_context, dict):
        return str(nexus_context)
    compact = str(nexus_context.get("compact_text") or "").strip()
    if compact:
        return compact[:9000]
    summary = str(nexus_context.get("summary") or "")
    items = nexus_context.get("items") if isinstance(nexus_context.get("items"), list) else []
    lines = [summary] if summary else []
    for item in items[:5]:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "")
            reason = str(item.get("reason") or "")
            s = str(item.get("summary") or item.get("description") or item.get("content") or "")
            lines.append(f"- {title} ({reason}): {s[:220]}")
        else:
            lines.append(f"- {str(item)[:220]}")
    return "\n".join([x for x in lines if x]).strip()[:9000]


def _strip_high_risk_noise(text: str) -> str:
    t = str(text or "").lower()
    for noise in _ADVISORY_NOISE:
        t = t.replace(noise, " ")
    t = re.sub(r"\bdo\s+not\s+(execute|run)\b", " ", t)
    t = re.sub(r"\bdon't\s+(execute|run)\b", " ", t)
    return t


def _contains_high_risk_fallback_intent(text: str) -> bool:
    t = _strip_high_risk_noise(text)
    if any(re.search(rf"\b{re.escape(keyword)}\b", t) for keyword in _HIGH_RISK_EN):
        return True
    return any(keyword in t for keyword in _HIGH_RISK_JA)


def _infer_simple_fallback_target(text: str) -> str:
    t = _strip_high_risk_noise(text)
    if not t.strip():
        return ""
    if _contains_high_risk_fallback_intent(text):
        return ""
    explicit = re.findall(r"(?<![\w./-])([A-Za-z0-9_-]+\.html)\b", str(text or ""), flags=re.IGNORECASE)
    explicit = list(dict.fromkeys(explicit))
    if len(explicit) == 1:
        return explicit[0]
    if len(explicit) > 1:
        return ""
    has_create_intent = any(re.search(rf"\b{re.escape(keyword)}\b", t) for keyword in _CREATE_INTENT_EN) or any(
        keyword in str(text or "") for keyword in _CREATE_INTENT_JA
    )
    if not has_create_intent:
        return ""
    if any(keyword in t for keyword in _HTML_HINTS):
        return "index.html"
    return ""
