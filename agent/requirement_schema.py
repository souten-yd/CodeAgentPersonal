from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequirementCategoryScores(BaseModel):
    goal: float = 0.0
    scope: float = 0.0
    functional_requirements: float = 0.0
    non_functional_requirements: float = 0.0
    constraints: float = 0.0
    done_definition: float = 0.0


class RequirementDefinition(BaseModel):
    requirement_id: str
    source_task_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    user_input: str
    interpreted_goal: str = ""
    user_intent: str = ""
    task_type: str = "other"
    scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    answered_questions: list[dict] = Field(default_factory=list)
    requirement_completeness_score: float = 0.0
    category_scores: RequirementCategoryScores = Field(default_factory=RequirementCategoryScores)
    priority: str = "medium"
    done_definition: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    user_confirmed: bool = False
    ready_for_planning: bool = True
