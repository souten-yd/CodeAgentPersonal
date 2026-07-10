from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.atlas_auto_policy_presets import DEFAULT_AUTO_POLICY_PRESET_ID


class AtlasAutoVerificationRequest(BaseModel):
    pool_id: str
    item_id: str
    preset_id: str = DEFAULT_AUTO_POLICY_PRESET_ID
    workspace_id: str = "default"
    run_id: str = ""
    command_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasAutoVerificationResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    preset_id: str
    status: Literal["passed", "failed", "blocked", "skipped"]
    verification_result: dict[str, Any] = Field(default_factory=dict)
    command_id: str = ""
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    plan_pool: dict[str, Any] | None = None
    orchestration_summary: dict[str, Any] | None = None
    continuation_prompt: str = ""
