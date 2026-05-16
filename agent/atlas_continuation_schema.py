from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasContinuationSummary(BaseModel):
    workspace_id: str
    pool_id: str = ""
    run_id: str = ""
    status: str = ""
    current_goal: str = ""
    current_item_id: str = ""
    current_item_title: str = ""
    completed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    total_items: int = 0
    last_event_type: str = ""
    last_event_message: str = ""
    next_action: str = ""
    checkpoint_md_path: str = ""
    plan_pool_md_path: str = ""
    state_json_path: str = ""
    events_ndjson_path: str = ""
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
