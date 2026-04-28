from __future__ import annotations

import uuid
from typing import Callable

from agent.requirement_schema import RequirementCategoryScores, RequirementDefinition


class RequirementAnalyzer:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None]) -> None:
        self.llm_json_fn = llm_json_fn
        self._last_warnings: list[str] = []

    def get_last_warnings(self) -> list[str]:
        return list(self._last_warnings)

    def analyze(
        self,
        *,
        source_task_id: str,
        user_input: str,
        requirement_mode: str,
        planning_mode: str,
        prompt: str,
        nexus_context: dict,
        repository_context: str,
        existing_requirement: RequirementDefinition | None = None,
    ) -> RequirementDefinition:
        warnings: list[str] = []
        context_input = "\n\n".join([
            f"User Input:\n{user_input}",
            f"Requirement Mode: {requirement_mode}",
            f"Planning Mode: {planning_mode}",
            f"Nexus Context: {nexus_context}",
            f"Repository Context: {repository_context}",
        ])
        raw_payload = self.llm_json_fn(prompt, context_input)
        if raw_payload is None:
            warnings.append("Requirement analysis LLM output could not be parsed. Fallback requirement was generated.")
            payload: dict = {}
        elif not isinstance(raw_payload, dict):
            warnings.append("Requirement analysis LLM output was not a JSON object. Fallback requirement was generated.")
            payload = {}
        else:
            payload = raw_payload
            if not payload:
                warnings.append("Requirement analysis LLM output was empty. Fallback requirement was generated.")

        requirement_id = existing_requirement.requirement_id if existing_requirement else f"req_{uuid.uuid4().hex[:12]}"
        category_scores = payload.get("category_scores") or {}
        req = RequirementDefinition(
            requirement_id=requirement_id,
            source_task_id=source_task_id,
            user_input=user_input,
            interpreted_goal=str(payload.get("interpreted_goal", user_input[:120])),
            user_intent=str(payload.get("user_intent", "Solve user request safely and incrementally.")),
            task_type=str(payload.get("task_type", _guess_task_type(user_input))),
            scope=_as_str_list(payload.get("scope")),
            out_of_scope=_as_str_list(payload.get("out_of_scope")),
            functional_requirements=_as_str_list(payload.get("functional_requirements")),
            non_functional_requirements=_merge_non_functional(payload.get("non_functional_requirements")),
            constraints=_as_str_list(payload.get("constraints")),
            assumptions=_as_str_list(payload.get("assumptions")),
            open_questions=payload.get("open_questions") or [],
            answered_questions=existing_requirement.answered_questions if existing_requirement else [],
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
            clarification_status=existing_requirement.clarification_status if existing_requirement else "not_needed",
            ready_for_planning=existing_requirement.ready_for_planning if existing_requirement else True,
            user_confirmed=False,
        )
        if not req.functional_requirements:
            req.functional_requirements = ["ユーザー入力に沿った実装計画を作成する"]
            warnings.append("Requirement payload did not include functional_requirements. Fallback requirement item was generated.")
        if not req.done_definition:
            req.done_definition = ["実装前の計画が合意可能な品質で提示されること"]
            warnings.append("Requirement payload did not include done_definition. Fallback done_definition was generated.")

        self._last_warnings = warnings
        return req


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _guess_task_type(user_input: str) -> str:
    text = user_input.lower()
    if any(k in text for k in ["bug", "fix", "バグ", "不具合"]):
        return "bugfix"
    if any(k in text for k in ["ui", "画面", "デザイン"]):
        return "ui"
    if any(k in text for k in ["refactor", "リファクタ"]):
        return "refactor"
    if any(k in text for k in ["project", "新規", "generate", "生成"]):
        return "project_generation"
    if any(k in text for k in ["investigate", "調査"]):
        return "investigation"
    return "feature"


def _merge_non_functional(raw_value) -> list[str]:
    existing = _as_str_list(raw_value)
    minimums = [
        "安定性（既存動作を壊さない）",
        "保守性（責務分離・読みやすさ）",
        "UI/UX（既存UIとの一貫性）",
        "iPhone Safari対応（表示崩れ回避）",
        "Docker / Runpod / Windowsローカル対応",
        "セキュリティ（危険な自動実行をしない）",
        "データ保存（JSON/Markdownの整合性）",
        "ログ（warning可視化）",
        "エラー時の復旧性（busy解除・再試行可能）",
        "既存機能との互換性",
    ]
    merged = list(existing)
    for item in minimums:
        if not any(item.split("（")[0] in x for x in merged):
            merged.append(item)
    return merged
