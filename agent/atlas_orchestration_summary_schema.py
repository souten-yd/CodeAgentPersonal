from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasOrchestrationSummary(BaseModel):
    pool_id: str = ""
    run_id: str = ""
    status: str = ""
    phase: str = ""
    current_item_id: str = ""
    current_item_title: str = ""
    next_action: str = ""
    user_message: str = ""
    severity: str = "info"
    can_start_dry_run: bool = False
    can_refresh_status: bool = False
    can_load_plan: bool = False
    can_continue: bool = False
    requires_clarification: bool = False
    requires_approval: bool = False
    is_stale: bool = False
    is_terminal: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
