from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AtlasDebugSourceType = Literal[
    "test_command",
    "safe_apply",
    "pipeline",
    "verification",
    "manual",
]

AtlasDebugAttemptStatus = Literal[
    "proposed",
    "skipped",
    "retry_allowed",
    "retry_blocked",
    "max_retries_reached",
    "failed",
    "completed",
]

AtlasDebugRootCauseCategory = Literal[
    "syntax_error",
    "import_error",
    "test_failure",
    "command_blocked",
    "timeout",
    "policy_blocked",
    "approval_missing",
    "executor_error",
    "missing_file",
    "invalid_config",
    "unknown",
]


class AtlasDebugInput(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    source_type: AtlasDebugSourceType
    error_summary: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    status: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasDebugAttempt(BaseModel):
    attempt_id: str = Field(default_factory=lambda: f"atlas_debug_attempt_{uuid4().hex}")
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    source_type: AtlasDebugSourceType
    status: AtlasDebugAttemptStatus = "proposed"
    retry_count: int = 0
    max_retries: int = 2
    root_cause_category: AtlasDebugRootCauseCategory = "unknown"
    error_summary: str = ""
    root_cause: str = ""
    proposed_fix: str = ""
    retry_recommended: bool = False
    retry_block_reason: str = ""
    related_files: list[str] = Field(default_factory=list)
    reusable_lesson: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)


class AtlasDebugLoopState(BaseModel):
    loop_id: str = Field(default_factory=lambda: f"atlas_debug_loop_{uuid4().hex}")
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    attempts: list[AtlasDebugAttempt] = Field(default_factory=list)
    status: AtlasDebugAttemptStatus = "proposed"
    max_retries: int = 2
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)
