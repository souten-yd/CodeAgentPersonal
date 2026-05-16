from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasSafeApplyExecutionRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    requested_by: str = "user"
    dry_run: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasSafeApplyExecutionResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    status: str
    safe_apply_result: dict = Field(default_factory=dict)
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
