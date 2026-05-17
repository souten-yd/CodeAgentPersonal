from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasPatchProposalPlanItemDraftRequest(BaseModel):
    pool_id: str
    item_id: str
    proposal_id: str = ""
    run_id: str = ""
    workspace_id: str = "default"
    requested_by: str = "user"
    metadata: dict = Field(default_factory=dict)


class AtlasPatchProposalPlanItemDraft(BaseModel):
    draft_item_id: str
    source_item_id: str
    source_proposal_id: str
    pool_id: str
    run_id: str = ""
    title: str = ""
    description: str = ""
    item_type: str = "implementation"
    status: str = "approval_required"
    risk_level: str = "low"
    target_files: list[str] = Field(default_factory=list)
    expected_changes: list[dict] = Field(default_factory=list)
    verification_plan: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = True
    metadata: dict = Field(default_factory=dict)


class AtlasPatchProposalPlanItemDraftResult(BaseModel):
    pool_id: str
    item_id: str
    proposal_id: str = ""
    status: str
    draft_item: AtlasPatchProposalPlanItemDraft | None = None
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
