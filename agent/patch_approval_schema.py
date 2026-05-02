from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PatchApprovalStatus = Literal["pending", "approved", "rejected", "applied", "expired"]
PatchApprovalDecision = Literal["approve", "reject", "none"]


class PatchApprovalRecord(BaseModel):
    patch_approval_id: str
    patch_id: str
    run_id: str
    plan_id: str
    step_id: str
    target_file: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    status: PatchApprovalStatus = "pending"
    decision: PatchApprovalDecision = "none"
    approved_by: str = ""
    user_comment: str = ""
    risk_acknowledged: bool = False
    safety_warnings_acknowledged: bool = False
    quality_warnings_acknowledged: bool = False
    low_quality_acknowledged: bool = False
    apply_allowed_at_approval: bool = False
    quality_score_at_approval: float = 0.0
    quality_warnings_at_approval: list[str] = Field(default_factory=list)
    quality_summary_at_approval: str = ""
    approved_for_apply: bool = False
    applied: bool = False
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class PatchApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    user_comment: str = ""
    risk_acknowledged: bool = False
    safety_warnings_acknowledged: bool = False
    quality_warnings_acknowledged: bool = False
    low_quality_acknowledged: bool = False
