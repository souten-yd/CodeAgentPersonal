from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasMultiItemAutopilotRequest(BaseModel):
    pool_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    item_ids: list[str] = Field(default_factory=list)
    policy_id: str = "guarded_multi_item_v1"
    context_policy_id: str = "local_first_bounded"
    evaluator_policy_id: str = "guarded_evaluator_v1"
    max_items: int = 3
    max_failures: int = 1
    max_runtime_seconds: int = 300
    max_changed_files_total: int = 20
    stop_on_manual_required: bool = True
    stop_on_revise: bool = True
    dry_run: bool = False
    require_approval: bool = True
    include_context_refresh: bool = True
    include_evaluator: bool = True
    include_bounded_retry: bool = False
    retry_policy_id: str = "verification_retry_v1"
    max_retry_attempts_per_item: int = 2
    include_self_correction: bool = True
    self_correction_max_attempts: int = 2
    metadata: dict = Field(default_factory=dict)


class AtlasMultiItemAutopilotPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    max_items: int = 3
    max_failures: int = 1
    max_runtime_seconds: int = 300
    max_changed_files_total: int = 20
    allowed_risk_levels: list[str] = Field(default_factory=lambda: ["low"])
    require_approval: bool = True
    require_context_refresh: bool = True
    require_verification: bool = True
    require_evaluator: bool = True
    continue_decisions: list[str] = Field(default_factory=lambda: ["continue"])
    stop_decisions: list[str] = Field(default_factory=lambda: ["stop", "manual_required", "revise"])
    allow_auto_restore: bool = False
    allow_auto_rollback: bool = False
    allow_auto_debug_review: bool = False
    allow_auto_patch_regeneration: bool = False
    notes: list[str] = Field(default_factory=list)


class AtlasAutopilotItemResult(BaseModel):
    item_id: str
    status: str
    reason: str = ""
    safe_apply_result: dict = Field(default_factory=dict)
    verification_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    context_bundle_id: str = ""
    evaluator_result_id: str = ""
    evaluator_decision: dict = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasMultiItemAutopilotResult(BaseModel):
    pool_id: str
    run_id: str
    autopilot_run_id: str
    policy_id: str
    status: str
    processed_count: int = 0
    completed_count: int = 0
    skipped_count: int = 0
    blocked_count: int = 0
    failed_count: int = 0
    item_results: list[AtlasAutopilotItemResult] = Field(default_factory=list)
    stop_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str
