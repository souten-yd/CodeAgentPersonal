from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ReviewSeverity = Literal["info", "warning", "high", "critical"]
ReviewCategory = Literal[
    "destructive_change",
    "large_scope_change",
    "dependency_change",
    "security",
    "data_loss",
    "api_breaking_change",
    "ui_breaking_change",
    "config_change",
    "missing_test",
    "requirement_mismatch",
    "nexus_context_mismatch",
    "ambiguous_step",
    "other",
]
ReviewRisk = Literal["low", "medium", "high", "critical"]
RecommendedNextAction = Literal["proceed", "ask_user", "revise_plan", "reject_plan"]


class PlanReviewFinding(BaseModel):
    finding_id: str
    severity: ReviewSeverity = "info"
    category: ReviewCategory = "other"
    title: str
    detail: str = ""
    related_steps: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)
    recommendation: str = ""
    requires_user_confirmation: bool = False


class PlanReviewResult(BaseModel):
    review_id: str
    plan_id: str
    requirement_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    overall_risk: ReviewRisk = "low"
    approved_for_execution: bool = True
    requires_user_confirmation: bool = False
    destructive_change_detected: bool = False
    findings: list[PlanReviewFinding] = Field(default_factory=list)
    blocking_findings: list[str] = Field(default_factory=list)
    summary: str = "No significant risk detected."
    recommended_next_action: RecommendedNextAction = "proceed"
    warnings: list[str] = Field(default_factory=list)
