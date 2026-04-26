from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "completed", "failed", "degraded"]


class NexusJob(BaseModel):
    """Nexus ジョブの最小スキーマ。"""

    job_id: str
    status: JobStatus = "queued"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NexusJobEvent(BaseModel):
    """Nexus ジョブイベントの最小スキーマ。"""

    seq: int = Field(ge=0)
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime | None = None
    status: JobStatus | None = None
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    message: str | None = None
    updated_at: datetime | None = None
