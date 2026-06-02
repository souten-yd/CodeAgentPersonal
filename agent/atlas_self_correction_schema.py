from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasSelfCorrectionRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    # The verification failure that triggers correction (stdout_tail/stderr_tail/exit_code/command/status).
    verification_result: dict = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    file_results: list[dict] = Field(default_factory=list)
    max_attempts: int = 2
    # Risk levels eligible for automatic re-apply. Default low/medium keeps the human-review
    # guard on high/critical; callers may widen it explicitly.
    risk_levels: list[str] = Field(default_factory=lambda: ["low", "medium"])


class AtlasSelfCorrectionResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    # not_attempted | skipped | recovered | exhausted | regen_failed | reapply_failed | failed
    status: str = "not_attempted"
    reason: str = ""
    attempts: int = 0
    final_verification_status: str = ""
    changed_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""
