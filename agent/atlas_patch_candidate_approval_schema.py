from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasPatchCandidateApprovalRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    regen_run_id: str
    proposal_id: str = ""
    decision: str
    reviewer: str = "manual"
    reason: str = ""
    policy_id: str = "patch_candidate_approval_v1"
    require_fresh_regen_result: bool = True
    create_safe_apply_handoff: bool = True
    metadata: dict = Field(default_factory=dict)


class AtlasPatchCandidateApprovalPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    require_manual_decision: bool = True
    allow_only_proposal_ready: bool = True
    require_candidate_validation_passed: bool = True
    require_target_files_match: bool = True
    require_no_secret_warnings: bool = True
    require_no_blocking_errors: bool = True
    allow_safe_apply_handoff: bool = True
    allow_safe_apply_execution: bool = False
    allow_verification_execution: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    max_patch_chars: int = 48000
    max_target_files: int = 10
    notes: list[str] = Field(default_factory=list)


class AtlasSafeApplyHandoff(BaseModel):
    handoff_id: str
    status: str
    pool_id: str
    item_id: str
    run_id: str = ""
    regen_run_id: str
    proposal_id: str
    patch: str = ""
    patch_format: str = "unified_diff"
    target_files: list[str] = Field(default_factory=list)
    source: str = "patch_regen_candidate"
    approval_status: str = "pending"
    safe_apply_ready: bool = False
    safe_apply_executed: bool = False
    verification_executed: bool = False
    gate_decision: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasPatchCandidateApprovalResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    regen_run_id: str
    proposal_id: str
    approval_run_id: str
    policy_id: str
    status: str
    decision: str
    reviewer: str
    reason: str = ""
    handoff: AtlasSafeApplyHandoff | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
