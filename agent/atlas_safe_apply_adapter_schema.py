from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


AtlasSafeApplyDecision = Literal["allow", "require_approval", "block"]
AtlasSafeApplyStatus = Literal["simulated", "applied", "skipped", "blocked", "failed"]
AtlasSafeApplyReasonCategory = Literal[
    "low_risk",
    "non_low_risk",
    "create_allowed",
    "update_allowed",
    "delete_forbidden",
    "run_command_forbidden",
    "protected_path",
    "policy_blocked",
    "policy_requires_approval",
    "approval_missing",
    "approval_present",
    "executor_missing",
    "executor_error",
    "unsupported_action",
    "safe_apply_disabled",
]


class AtlasSafeApplyRequest(BaseModel):
    pool_id: str
    item_id: str
    dry_run: bool = False
    require_approval: bool = True
    allow_simulation_without_executor: bool = True
    metadata: dict = Field(default_factory=dict)


class AtlasSafeApplyResult(BaseModel):
    pool_id: str
    item_id: str
    status: AtlasSafeApplyStatus
    decision: AtlasSafeApplyDecision
    applied: bool = False
    simulated: bool = False
    implementation_run_id: str = ""
    reasons: list[str] = Field(default_factory=list)
    categories: list[AtlasSafeApplyReasonCategory] = Field(default_factory=list)
    executor_result: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)
