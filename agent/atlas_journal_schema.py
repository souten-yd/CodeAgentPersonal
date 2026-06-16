from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


AtlasJournalArtifactType = Literal[
    "checkpoint",
    "master_plan",
    "decisions",
    "next_actions",
    "plan_pool",
    "pipeline_state",
    "event_log",
    "approval_log",
    "verification",
    "diff_summary",
    "final_report",
    "debug_notes",
    "context_pack",
]

AtlasRecoveryStatus = Literal[
    "no_workspace",
    "no_plan_pool",
    "no_pipeline_run",
    "ready",
    "running",
    "paused",
    "completed",
    "failed",
    "blocked",
    "stale",
    "interrupted",
]


class AtlasJournalPaths(BaseModel):
    workspace_id: str
    root_dir: str
    workspace_dir: str
    plan_pool_dir: str = ""
    pipeline_run_dir: str = ""
    checkpoint_md: str = ""
    plan_pool_json: str = ""
    plan_pool_md: str = ""
    pipeline_state_json: str = ""
    pipeline_state_md: str = ""
    events_ndjson: str = ""
    final_report_md: str = ""
    approvals_json: str = ""
    approvals_md: str = ""


class AtlasJournalArtifact(BaseModel):
    artifact_id: str
    artifact_type: AtlasJournalArtifactType
    json_path: str = ""
    markdown_path: str = ""
    ndjson_path: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)


class AtlasRecoverySummary(BaseModel):
    workspace_id: str
    pool_id: str = ""
    run_id: str = ""
    status: AtlasRecoveryStatus
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
    state_json_path: str = ""
    events_ndjson_path: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
