from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


QuestionType = Literal["single_choice", "multiple_choice", "free_text", "yes_no"]
QuestionImportance = Literal["required", "recommended", "optional"]
ClarificationStatus = Literal["not_needed", "waiting", "answered", "skipped"]


class RequirementCategoryScores(BaseModel):
    goal: float = 0.0
    scope: float = 0.0
    functional_requirements: float = 0.0
    non_functional_requirements: float = 0.0
    constraints: float = 0.0
    done_definition: float = 0.0


class ClarificationQuestion(BaseModel):
    question_id: str
    question: str
    reason: str = ""
    type: QuestionType = "single_choice"
    importance: QuestionImportance = "recommended"
    options: list[str] = Field(default_factory=list)
    default: str | list[str] | None = None
    answered: bool = False
    answer: str | list[str] | bool | dict[str, Any] | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    answered_at: str | None = None


class ClarificationResult(BaseModel):
    requirement_id: str
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    can_continue_without_answers: bool = True
    blocking_questions: list[str] = Field(default_factory=list)
    assumptions_if_skipped: list[str] = Field(default_factory=list)


class RequirementDefinition(BaseModel):
    requirement_id: str
    source_task_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    user_input: str
    project_name: str = ""
    project_path: str = ""
    resolved_project_path: str = ""
    interpreted_goal: str = ""
    user_intent: str = ""
    task_type: str = "other"
    scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[ClarificationQuestion] = Field(default_factory=list)
    answered_questions: list[ClarificationQuestion] = Field(default_factory=list)
    clarification_status: ClarificationStatus = "not_needed"
    requirement_completeness_score: float = 0.0
    category_scores: RequirementCategoryScores = Field(default_factory=RequirementCategoryScores)
    priority: str = "medium"
    done_definition: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    user_confirmed: bool = False
    ready_for_planning: bool = True

    @field_validator("open_questions", mode="before")
    @classmethod
    def _normalize_open_questions(cls, value):
        return _normalize_question_list(value)

    @field_validator("answered_questions", mode="before")
    @classmethod
    def _normalize_answered_questions(cls, value):
        return _normalize_question_list(value, answered_default=True)

    @model_validator(mode="after")
    def _sync_ready_state(self):
        if self.open_questions:
            has_required_open = any(q.importance == "required" and not q.answered for q in self.open_questions)
            if has_required_open:
                self.ready_for_planning = False
                if self.clarification_status in {"not_needed", "answered"}:
                    self.clarification_status = "waiting"
            elif self.clarification_status == "not_needed":
                self.clarification_status = "answered"
        else:
            if self.answered_questions and self.clarification_status == "waiting":
                self.clarification_status = "answered"
            if self.clarification_status == "waiting":
                self.clarification_status = "answered"
            if self.clarification_status == "not_needed":
                self.ready_for_planning = True
            elif self.clarification_status in {"answered", "skipped"}:
                self.ready_for_planning = True
        return self


def _normalize_question_list(value, *, answered_default: bool = False) -> list[ClarificationQuestion]:
    if not value:
        return []
    normalized: list[ClarificationQuestion] = []
    if isinstance(value, list):
        for i, item in enumerate(value, start=1):
            if isinstance(item, ClarificationQuestion):
                normalized.append(item)
                continue
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                normalized.append(
                    ClarificationQuestion(
                        question_id=f"legacy_q_{i}",
                        question=text,
                        reason="Legacy migrated question",
                        type=_infer_legacy_question_type(text),
                        importance="recommended",
                        options=["おまかせ"],
                        default="おまかせ",
                        answered=answered_default,
                        answer=_normalize_legacy_answer("おまかせ") if answered_default else None,
                    )
                )
                continue
            if isinstance(item, dict):
                q = dict(item)
                q.setdefault("question_id", str(q.get("id") or f"legacy_q_{i}"))
                q.setdefault("question", str(q.get("question") or q.get("text") or ""))
                q.setdefault("reason", str(q.get("reason") or ""))
                q.setdefault("type", "free_text")
                q.setdefault("importance", "recommended")
                q.setdefault("options", q.get("options") or ["おまかせ"])
                q.setdefault("default", q.get("default", "おまかせ"))
                q.setdefault("answered", bool(q.get("answered", answered_default)))
                q["answer"] = _normalize_legacy_answer(q.get("answer"))
                if q.get("answered") and q.get("answered_at") is None:
                    q["answered_at"] = _utc_now_iso()
                normalized.append(ClarificationQuestion(**q))
    return normalized
def _normalize_legacy_answer(answer: Any) -> Any:
    if isinstance(answer, dict):
        mode = str(answer.get("mode") or "custom").strip().lower() or "custom"
        text = str(answer.get("text") or "")
        raw_choice = answer.get("raw_choice")
        return {"mode": mode, "text": text, "raw_choice": raw_choice}
    if answer == "はい":
        return {"mode": "accept", "text": "", "raw_choice": "はい"}
    if answer == "いいえ":
        return {"mode": "reject", "text": "", "raw_choice": "いいえ"}
    if answer == "おまかせ":
        return {"mode": "delegate", "text": "", "raw_choice": "おまかせ"}
    return answer


def _infer_legacy_question_type(text: str) -> str:
    q = (text or "").strip().lower()
    yes_no_prefixes = ("should ", "do you want", "is ", "are ", "必要ですか", "含めますか")
    if q.startswith(yes_no_prefixes):
        return "yes_no"
    return "free_text"
