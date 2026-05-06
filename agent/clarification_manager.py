from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.requirement_schema import ClarificationQuestion, ClarificationResult, RequirementDefinition


class ClarificationManager:
    def generate(self, requirement: RequirementDefinition, requirement_mode: str, *, allow_derive: bool = True) -> ClarificationResult:
        limit = _question_limit(requirement_mode)
        normalized = self._normalize_questions(requirement, limit=limit, allow_derive=allow_derive)
        blocking = [q.question_id for q in normalized if q.importance == "required" and not q.answered]
        can_continue = not blocking
        assumptions = [f"{q.question}: {self._default_answer_text(q)}" for q in normalized if not q.answered and q.importance != "required"]
        return ClarificationResult(
            requirement_id=requirement.requirement_id,
            questions=normalized,
            can_continue_without_answers=can_continue,
            blocking_questions=blocking,
            assumptions_if_skipped=assumptions,
        )

    def apply_answers(self, requirement: RequirementDefinition, answers: list[dict]) -> RequirementDefinition:
        answer_map = {str(item.get("question_id")): item.get("answer") for item in answers if isinstance(item, dict)}
        now = _utc_now_iso()
        remaining: list[ClarificationQuestion] = []
        answered = list(requirement.answered_questions)

        for q in requirement.open_questions:
            if q.question_id not in answer_map:
                remaining.append(q)
                continue
            answer = self._normalize_answer(answer_map[q.question_id])
            if answer is None:
                remaining.append(q)
                continue
            nq = q.model_copy(deep=True)
            nq.answered = True
            nq.answer = answer
            nq.answered_at = now
            answered.append(nq)

        requirement.open_questions = remaining
        requirement.answered_questions = answered

        if not requirement.open_questions:
            requirement.clarification_status = "answered"
            requirement.ready_for_planning = True
        else:
            has_required_open = any(q.importance == "required" and not q.answered for q in requirement.open_questions)
            requirement.clarification_status = "waiting" if has_required_open else "answered"
            requirement.ready_for_planning = not has_required_open
        requirement.updated_at = now
        return requirement

    def _normalize_answer(self, answer: Any) -> Any:
        if isinstance(answer, dict):
            mode = str(answer.get("mode") or "custom").strip().lower() or "custom"
            text = str(answer.get("text") or "")
            raw_choice = answer.get("raw_choice")
            if mode == "custom" and isinstance(raw_choice, str):
                if raw_choice == "はい":
                    mode = "accept"
                elif raw_choice == "いいえ":
                    mode = "reject"
                elif raw_choice == "おまかせ":
                    mode = "delegate"
            return {"mode": mode, "text": text, "raw_choice": raw_choice}
        if answer == "はい":
            return {"mode": "accept", "text": "", "raw_choice": "はい"}
        if answer == "いいえ":
            return {"mode": "reject", "text": "", "raw_choice": "いいえ"}
        if answer == "おまかせ":
            return {"mode": "delegate", "text": "", "raw_choice": "おまかせ"}
        return answer

    def skip_with_defaults(self, requirement: RequirementDefinition) -> RequirementDefinition:
        payload = []
        for q in requirement.open_questions:
            payload.append({"question_id": q.question_id, "answer": q.default if q.default is not None else "おまかせ"})
        updated = self.apply_answers(requirement, payload)
        updated.clarification_status = "skipped"
        updated.ready_for_planning = True
        return updated

    def unresolved_required_questions(self, requirement: RequirementDefinition) -> list[ClarificationQuestion]:
        return [q for q in requirement.open_questions if q.importance == "required" and not q.answered]

    def _normalize_questions(self, requirement: RequirementDefinition, *, limit: int, allow_derive: bool) -> list[ClarificationQuestion]:
        if _is_small_task((requirement.user_input or "").lower(), requirement.task_type):
            requirement.open_questions = []
            requirement.clarification_status = "not_needed"
            requirement.ready_for_planning = True
            return []

        questions = list(requirement.open_questions)
        if not questions and allow_derive:
            questions = self._derive_questions(requirement)

        normalized: list[ClarificationQuestion] = []
        for i, q in enumerate(questions, start=1):
            nq = q.model_copy(deep=True)
            if not nq.question_id:
                nq.question_id = f"q{i}"
            if nq.type == "yes_no":
                nq.options = ["はい", "いいえ", "おまかせ"]
            elif not nq.options:
                nq.options = ["おまかせ"]
            elif "おまかせ" not in nq.options:
                nq.options.append("おまかせ")
            if nq.default is None:
                nq.default = "おまかせ" if nq.type != "multiple_choice" else ["おまかせ"]
            inferred = _infer_importance(requirement, nq.question)
            if nq.importance == "recommended" and inferred != "recommended":
                nq.importance = inferred
            normalized.append(nq)

        normalized = _sort_questions(normalized)[:limit]
        requirement.open_questions = normalized

        if normalized:
            requirement.clarification_status = "waiting"
            requirement.ready_for_planning = not any(q.importance == "required" for q in normalized)
        else:
            requirement.clarification_status = "not_needed"
            requirement.ready_for_planning = True
        return normalized

    def _derive_questions(self, requirement: RequirementDefinition) -> list[ClarificationQuestion]:
        text = (requirement.user_input or "").lower()
        if _is_small_task(text, requirement.task_type):
            return []

        questions: list[ClarificationQuestion] = []
        if requirement.task_type in {"project_generation", "feature"} and any(k in text for k in ["新規", "project", "生成", "設計", "architecture", "アーキテクチャ"]):
            questions.append(
                ClarificationQuestion(
                    question_id="q_priority",
                    question="今回の実装で最も優先する方針はどれですか？",
                    reason="優先方針により設計案・作業順序が大きく変わるため",
                    type="single_choice",
                    importance="required",
                    options=[
                        "最小構成で早く動かす",
                        "将来拡張しやすい構成にする",
                        "UI/UX品質を優先する",
                        "安定性・エラー復旧を優先する",
                        "おまかせ",
                    ],
                    default="おまかせ",
                )
            )

        if "database" in text or "db" in text or "保存" in text:
            questions.append(
                ClarificationQuestion(
                    question_id="q_data",
                    question="データ保存方式の優先はありますか？",
                    reason="保存方式で依存・構成が変わるため",
                    type="single_choice",
                    importance="recommended",
                    options=["既存方式に合わせる", "SQLite", "JSONファイル", "外部DB", "おまかせ"],
                    default="既存方式に合わせる",
                )
            )

        if "公開" in text or "security" in text or "認証" in text:
            questions.append(
                ClarificationQuestion(
                    question_id="q_security",
                    question="外部公開や認証強化は今回の必須範囲ですか？",
                    reason="セキュリティ要件の有無で完了条件が変わるため",
                    type="yes_no",
                    importance="required",
                    options=["Yes", "No", "おまかせ"],
                    default="No",
                )
            )

        if not questions and requirement.open_questions:
            questions = requirement.open_questions
        return questions

    def _default_answer_text(self, q: ClarificationQuestion) -> str:
        if q.default is None:
            return "おまかせ"
        if isinstance(q.default, list):
            return ", ".join([str(x) for x in q.default])
        return str(q.default)



def _infer_importance(requirement: RequirementDefinition, question: str) -> str:
    q = (question or "").lower()
    if any(k in q for k in ["優先", "方針", "architecture", "アーキ", "要件"]):
        return "required"
    if any(k in q for k in ["security", "セキュリティ", "公開", "認証"]):
        return "required"
    if any(k in q for k in ["保存", "db", "database"]):
        return "recommended"
    if requirement.task_type == "project_generation" and not requirement.answered_questions:
        return "required"
    return "recommended"


def _question_limit(requirement_mode: str) -> int:
    mode = (requirement_mode or "").strip().lower()
    if mode == "auto":
        return 2
    if mode in {"full_requirement_session", "full_session"}:
        return 7
    return 3


def _is_small_task(text: str, task_type: str) -> bool:
    small_keywords = ["typo", "文言", "小さ", "minor", "軽微", "表示崩れ", "css", "bugfix", "バグ修正"]
    return task_type in {"bugfix", "ui"} and any(k in text for k in small_keywords)


def _sort_questions(questions: list[ClarificationQuestion]) -> list[ClarificationQuestion]:
    order = {"required": 0, "recommended": 1, "optional": 2}
    return sorted(questions, key=lambda q: (order.get(q.importance, 3), q.question_id))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
