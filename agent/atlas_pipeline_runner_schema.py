from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AtlasPipelineRunStatus = Literal[
    "created",
    "running",
    "paused",
    "completed",
    "completed_with_warnings",
    "failed",
    "blocked",
    "cancelled",
]

AtlasPipelineItemRunStatus = Literal[
    "pending",
    "policy_checking",
    "approval_required",
    "dry_running",
    "completed",
    "failed",
    "blocked",
    "skipped",
]

AtlasPipelineEventType = Literal[
    "pipeline_created",
    "pipeline_started",
    "policy_evaluated",
    "item_started",
    "item_dry_run_started",
    "item_dry_run_completed",
    "item_research_started",
    "item_research_completed",
    "item_completed",
    "item_blocked",
    "item_failed",
    "pipeline_paused",
    "pipeline_completed",
    "pipeline_failed",
    "pipeline_blocked",
]


class AtlasPipelineRunRequest(BaseModel):
    run_id: str = ""
    pool_id: str
    ca_data_root: str = ""
    execution_strategy: str = "sequential"
    max_items: int | None = None
    dry_run: bool = True
    safe_apply: bool = False
    stop_on_failure: bool = True
    pause_after_each_item: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasPipelineItemResult(BaseModel):
    item_id: str
    status: AtlasPipelineItemRunStatus = "pending"
    policy_decision: str = ""
    policy_reasons: list[str] = Field(default_factory=list)
    policy_categories: list[str] = Field(default_factory=list)
    implementation_run_id: str = ""
    dry_run_result: dict = Field(default_factory=dict)
    context_pack_id: str = ""
    context_pack_result: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


class AtlasPipelineEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: AtlasPipelineEventType
    item_id: str = ""
    message: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)


class AtlasPipelineRunState(BaseModel):
    run_id: str
    pool_id: str
    status: AtlasPipelineRunStatus = "created"
    current_item_id: str = ""
    completed_item_ids: list[str] = Field(default_factory=list)
    blocked_item_ids: list[str] = Field(default_factory=list)
    failed_item_ids: list[str] = Field(default_factory=list)
    skipped_item_ids: list[str] = Field(default_factory=list)
    item_results: list[AtlasPipelineItemResult] = Field(default_factory=list)
    events: list[AtlasPipelineEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    finished_at: str = ""
    metadata: dict = Field(default_factory=dict)

    def add_event(
        self,
        event_type: AtlasPipelineEventType,
        item_id: str = "",
        message: str = "",
        metadata: dict | None = None,
    ) -> AtlasPipelineEvent:
        event = AtlasPipelineEvent(
            event_id=f"atlas_pipeline_event_{uuid4().hex}",
            run_id=self.run_id,
            event_type=event_type,
            item_id=item_id,
            message=message,
            metadata=metadata or {},
        )
        self.events.append(event)
        self.updated_at = _utc_now_iso()
        return event

    def get_item_result(self, item_id: str) -> AtlasPipelineItemResult | None:
        for result in self.item_results:
            if result.item_id == item_id:
                return result
        return None
