from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AtlasEvaluatorTrigger = Literal["post_safe_apply", "post_verification", "verification_failure", "evaluator_precheck", "manual"]
AtlasEvaluatorDecisionType = Literal["continue", "stop", "revise", "manual_required"]
AtlasEvaluatorStatus = Literal["evaluated", "fallback_evaluated", "blocked", "failed", "skipped"]


class AtlasEvaluatorRequest(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    workspace_id: str = "default"
    trigger: AtlasEvaluatorTrigger
    context_bundle_id: str = ""
    use_latest_context_bundle: bool = True
    project_path: str = ""
    changed_files: list[str] = Field(default_factory=list)
    verification_result: dict = Field(default_factory=dict)
    safe_apply_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    policy_id: str = "guarded_evaluator_v1"
    max_prompt_chars: int = 48000
    metadata: dict = Field(default_factory=dict)


class AtlasEvaluatorPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    allow_llm: bool = True
    allow_fallback_without_llm: bool = True
    require_context_bundle: bool = False
    require_verification_result_for_continue: bool = True
    allow_continue_on_failed_verification: bool = False
    max_prompt_chars: int = 48000
    max_context_chars: int = 24000
    max_diff_chars: int = 12000
    max_sources: int = 12
    confidence_threshold_continue: float = 0.75
    notes: list[str] = Field(default_factory=list)


class AtlasEvaluationInputPacket(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    trigger: str
    policy_id: str
    changed_files: list[str] = Field(default_factory=list)
    context_bundle: dict = Field(default_factory=dict)
    diff_summary: str = ""
    verification_result: dict = Field(default_factory=dict)
    safe_apply_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    related_tests: list[dict] = Field(default_factory=list)
    dependency_edges: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasEvaluatorDecision(BaseModel):
    decision: AtlasEvaluatorDecisionType = "manual_required"
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    requires_manual_review: bool = True
    should_run_debug_review: bool = False
    should_generate_patch_proposal: bool = False
    should_restore: bool = False
    should_continue_autopilot: bool = False
    summary: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasEvaluatorResult(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    trigger: str
    policy_id: str
    status: AtlasEvaluatorStatus
    decision: AtlasEvaluatorDecision
    input_packet: AtlasEvaluationInputPacket
    context_bundle_id: str = ""
    prompt_preview: str = ""
    raw_llm_output: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str
