from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "completed", "failed"]


class NexusJob(BaseModel):
    """Nexus ジョブの最小スキーマ。"""

    job_id: str
    status: JobStatus = "queued"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NexusJobEvent(BaseModel):
    """Nexus ジョブイベントの最小スキーマ。"""

    seq: int = Field(ge=0)
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime | None = None
