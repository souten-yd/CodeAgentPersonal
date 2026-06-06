from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasPatchProposalRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    requested_by: str = "user"
    source_type: str = "debug_review"
    proposal_mode: str = "standard"
    metadata: dict = Field(default_factory=dict)
    force_regenerate: bool = False


class AtlasPatchProposal(BaseModel):
    proposal_id: str
    pool_id: str
    item_id: str
    run_id: str = ""
    status: str = "proposed"
    title: str = ""
    summary: str = ""
    root_cause: str = ""
    proposed_fix: str = ""
    target_files: list[str] = Field(default_factory=list)
    suggested_changes: list[dict] = Field(default_factory=list)
    unified_diff_preview: str = ""
    risk_level: str = "medium"
    verification_plan: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasPatchProposalResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    status: str
    proposal: AtlasPatchProposal | None = None
    proposal_json_path: str = ""
    proposal_md_path: str = ""
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
