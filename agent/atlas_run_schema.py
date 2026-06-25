from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent.atlas_time_utils import utc_now_iso


AtlasRunStatus = Literal[
    "queued",
    "running",
    "waiting_for_user",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]

AtlasRunPhase = Literal[
    "queued",
    "planning",
    "proposal",
    "safe_apply",
    "verification",
    "repair",
    "final_summary",
]

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "blocked"})


class AtlasRunState(BaseModel):
    run_id: str
    pool_id: str
    workspace_id: str = "default"
    status: AtlasRunStatus = "queued"
    phase: AtlasRunPhase = "queued"
    mode: str = "fresh"
    current_item_id: str = ""
    current_item_index: int = 0
    total_items: int = 0
    completed_item_ids: list[str] = Field(default_factory=list)
    failed_item_ids: list[str] = Field(default_factory=list)
    blocked_item_ids: list[str] = Field(default_factory=list)
    skipped_item_ids: list[str] = Field(default_factory=list)
    requires_user_action: bool = False
    block_reason: str = ""
    error: str = ""
    next_actions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    finished_at: str = ""
    metadata: dict = Field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES


class AtlasRunEvent(BaseModel):
    sequence: int = 0
    run_id: str
    pool_id: str
    event_type: str
    phase: str = ""
    status: str = ""
    item_id: str = ""
    message: str = ""
    source: str = "backend"
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict = Field(default_factory=dict)

