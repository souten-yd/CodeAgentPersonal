from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasCIFailureRepairRequest(BaseModel):
    source: str = "manual"
    run_id: str = ""
    job_id: str = ""
    failing_command: str = ""
    log_text: str = ""
    failing_test_names: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    plan_items: list[dict] = Field(default_factory=list)


class AtlasCIFailureEvidence(BaseModel):
    source: str = "manual"
    run_id: str = ""
    job_id: str = ""
    failing_command: str = ""
    failing_test_names: list[str] = Field(default_factory=list)
    log_excerpt: str = ""
    affected_files: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    bounded_repair_recommendation: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasCIRepairPlan(BaseModel):
    status: str = "blocked"
    failure_class: str = "unknown"
    mapped_plan_item_ids: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    allowed_repair_files: list[str] = Field(default_factory=list)
    blocked_files: list[str] = Field(default_factory=list)
    post_repair_verification_required: bool = False
    recommended_verification_commands: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
