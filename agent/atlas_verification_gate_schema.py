from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasVerificationRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    requested_by: str = "user"
    verification_mode: str = "manual"
    command_profile: str = "default"
    metadata: dict = Field(default_factory=dict)


class AtlasVerificationResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    status: str
    verification_results: list[dict] = Field(default_factory=list)
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
