from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasPatchRegenRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    policy_id: str = "supervised_patch_regen_v1"
    context_bundle_id: str = ""
    retry_run_id: str = ""
    evaluator_result_id: str = ""
    verification_result: dict = Field(default_factory=dict)
    bounded_retry_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    original_patch: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    max_prompt_chars: int = 64000
    max_patch_chars: int = 48000
    dry_run: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasPatchRegenPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    allow_llm: bool = True
    allow_fallback_without_llm: bool = True
    require_context_bundle: bool = True
    require_failure_evidence: bool = True
    require_manual_approval: bool = True
    allow_auto_apply: bool = False
    allow_safe_apply: bool = False
    allow_verification: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    allow_auto_debug_review: bool = False
    allow_remote_git: bool = False
    max_prompt_chars: int = 64000
    max_patch_chars: int = 48000
    max_target_files: int = 10
    allowed_decisions: list[str] = Field(default_factory=lambda: ["proposal_ready", "manual_required", "not_regeneratable", "blocked"])
    notes: list[str] = Field(default_factory=list)


class AtlasPatchRegenInputPacket(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    policy_id: str
    project_path: str = ""
    target_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    original_patch_summary: str = ""
    original_patch: str = ""
    verification_result: dict = Field(default_factory=dict)
    bounded_retry_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    evaluator_result: dict = Field(default_factory=dict)
    context_bundle: dict = Field(default_factory=dict)
    related_tests: list[dict] = Field(default_factory=list)
    dependency_edges: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasPatchProposalCandidate(BaseModel):
    proposal_id: str
    status: str
    patch: str = ""
    patch_format: str = "unified_diff"
    target_files: list[str] = Field(default_factory=list)
    summary: str = ""
    rationale: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verification_suggestions: list[dict] = Field(default_factory=list)
    manual_review_required: bool = True
    approval_required: bool = True
    approval_status: str = "pending"
    safe_apply_ready: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasPatchRegenResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    regen_run_id: str
    policy_id: str
    status: str
    candidate: AtlasPatchProposalCandidate
    input_packet: AtlasPatchRegenInputPacket
    context_bundle_id: str = ""
    retry_run_id: str = ""
    evaluator_result_id: str = ""
    prompt_preview: str = ""
    raw_llm_output: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
