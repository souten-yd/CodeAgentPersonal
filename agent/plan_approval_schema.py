from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ApprovalStatus = Literal["pending", "approved", "revision_requested", "rejected", "expired"]
ApprovalDecision = Literal["approve", "request_revision", "reject", "none"]


class PlanApprovalRecord(BaseModel):
    approval_id: str
    plan_id: str
    requirement_id: str
    review_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    status: ApprovalStatus = "pending"
    decision: ApprovalDecision = "none"
    approved_for_execution: bool = False
    approved_by: str = "user"
    user_comment: str = ""
    revision_request: str = ""
    risk_acknowledged: bool = False
    destructive_change_acknowledged: bool = False
    review_overall_risk: str = "low"
    requires_user_confirmation: bool = False
    execution_ready: bool = False
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanApprovalRequest(BaseModel):
    decision: Literal["approve", "request_revision", "reject"]
    user_comment: str = ""
    revision_request: str = ""
    risk_acknowledged: bool = False
    destructive_change_acknowledged: bool = False
