from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasAutonomousCodegenRequest(BaseModel):
    """Request for the end-to-end autonomous code generation orchestrator.

    The orchestrator drives goal->plan(existing pool)->batch patch generation->multi-item apply
    ->verify->self-correct in a single call under the full-automation profile. It only *composes*
    existing services, so the multi-item engine, gates and safety relaxation are unchanged.
    """

    pool_id: str
    user_requirement: str = ""
    run_id: str = ""
    orchestrator_run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    item_ids: list[str] = Field(default_factory=list)
    selected_profile: str = "review_only"
    selected_preset: str = "guarded_low_risk"
    envelope: dict = Field(default_factory=dict)
    max_actions: int = 20
    max_items: int = 20
    max_retries: int = 2
    max_runtime_seconds: int = 600
    max_changed_files_total: int = 20
    max_changed_files_per_item: int = 8
    allowed_paths: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)
    allowed_verification_commands: list[str] = Field(default_factory=list)
    clarification_mode: str = "pause"
    critical_handling: str = "ask"
    self_improvement: bool = False
    # The multi-item policy that opts into full automation (low/medium/high create/update,
    # no per-item approval). Critical risk + delete/run_command stay blocked downstream.
    policy_id: str = "full_auto_multi_item_v1"
    # Phase 2: generate a first patch for any item that has no applicable content yet.
    generate_missing_patches: bool = True
    metadata: dict = Field(default_factory=dict)


class AtlasAutonomousCodegenProposalResult(BaseModel):
    item_id: str
    status: str
    patch_content_available: bool = False
    reason: str = ""


class AtlasAutonomousCodegenResult(BaseModel):
    pool_id: str
    run_id: str
    orchestrator_run_id: str
    # Lifecycle phase reached: load -> safety_gate -> patch_generation -> apply -> completed.
    phase: str = "load"
    # Aggregate status: completed / partial / stopped / blocked / failed / blocked_safety_review /
    # no_items. Mirrors the multi-item autopilot status, plus orchestrator-only terminal states.
    status: str = "running"
    generated_count: int = 0
    skipped_generation_count: int = 0
    proposal_results: list[AtlasAutonomousCodegenProposalResult] = Field(default_factory=list)
    autopilot_result: dict = Field(default_factory=dict)
    stop_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str
