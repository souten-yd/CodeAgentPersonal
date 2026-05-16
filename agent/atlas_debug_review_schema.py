from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasDebugReviewRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    requested_by: str = "user"
    source_type: str = "verification"
    metadata: dict = Field(default_factory=dict)


class AtlasDebugReviewResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    status: str
    debug_attempt: dict = Field(default_factory=dict)
    debug_notes_path: str = ""
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
