from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AtlasTestCommandStatus = Literal[
    "pending",
    "skipped",
    "running",
    "passed",
    "failed",
    "blocked",
    "timed_out",
]

AtlasTestCommandBlockReason = Literal[
    "empty_command",
    "not_allowlisted",
    "forbidden_token",
    "shell_operator",
    "working_directory_invalid",
    "timeout_invalid",
]


class AtlasTestCommandRequest(BaseModel):
    command: str
    cwd: str = ""
    timeout_seconds: int = 120
    metadata: dict = Field(default_factory=dict)


class AtlasTestCommandResult(BaseModel):
    command: str
    status: AtlasTestCommandStatus
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    blocked_reason: AtlasTestCommandBlockReason | str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasTestCommandBatchResult(BaseModel):
    results: list[AtlasTestCommandResult] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    timed_out_count: int = 0
    skipped_count: int = 0
    metadata: dict = Field(default_factory=dict)
