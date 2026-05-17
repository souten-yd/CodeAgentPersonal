from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasPatchProposalApprovalRequest(BaseModel):
    pool_id: str
    item_id: str
    proposal_id: str = ""
    run_id: str = ""
    workspace_id: str = "default"
    decision: str
    reason: str = ""
    approver: str = "user"
    metadata: dict = Field(default_factory=dict)


class AtlasPatchProposalApprovalRecord(BaseModel):
    approval_id: str
    pool_id: str
    item_id: str
    proposal_id: str
    run_id: str = ""
    decision: str
    reason: str = ""
    approver: str = "user"
    decided_at: str
    proposal_summary: str = ""
    proposal_risk_level: str = ""
    proposal_md_path: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasPatchProposalApprovalResult(BaseModel):
    pool_id: str
    item_id: str
    proposal_id: str = ""
    status: str
    approval_record: AtlasPatchProposalApprovalRecord | None = None
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
