from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AtlasPlanItemType = Literal[
    "research",
    "planning",
    "implementation",
    "verification",
    "documentation",
    "nexus_save",
]

AtlasPlanItemStatus = Literal[
    "queued",
    "ready",
    "researching",
    "planning",
    "reviewing",
    "approval_required",
    "approved",
    "executing",
    "testing",
    "debugging",
    "completed",
    "blocked",
    "needs_revision",
    "failed",
    "skipped",
    "cancelled",
]

AtlasPlanPoolStatus = Literal[
    "draft",
    "ready",
    "approval_required",
    "approved",
    "running",
    "paused",
    "completed",
    "completed_with_warnings",
    "failed",
    "blocked",
    "cancelled",
]

AtlasPlanningDepth = Literal["quick", "standard", "deep_nexus"]
AtlasAutomationLevel = Literal[
    "plan_only",
    "plan_then_ask",
    "auto_after_approval",
    "full_autopilot",
]
AtlasExecutionStrategy = Literal["sequential", "pause_after_each_item", "manual_gated"]
AtlasRiskLevel = Literal["low", "medium", "high", "critical"]
AtlasPriority = Literal["low", "medium", "high"]


class AtlasPlanItem(BaseModel):
    item_id: str
    pool_id: str
    title: str
    goal: str
    parent_plan_id: str = ""
    description: str = ""
    item_type: AtlasPlanItemType = "implementation"
    status: AtlasPlanItemStatus = "queued"
    priority: AtlasPriority = "medium"
    risk_level: AtlasRiskLevel = "medium"
    depends_on: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    expected_changes: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    done_definition: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = False
    auto_execution_allowed: bool = False
    linked_requirement_id: str = ""
    linked_plan_id: str = ""
    linked_run_id: str = ""
    linked_context_pack_id: str = ""
    approval_id: str = ""
    execution_preview_id: str = ""
    retry_count: int = 0
    max_retries: int = 2
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)


class AtlasPlanPool(BaseModel):
    pool_id: str
    root_goal: str
    project_path: str = ""
    project_name: str = ""
    planning_depth: AtlasPlanningDepth = "standard"
    automation_level: AtlasAutomationLevel = "plan_then_ask"
    execution_strategy: AtlasExecutionStrategy = "sequential"
    status: AtlasPlanPoolStatus = "draft"
    items: list[AtlasPlanItem] = Field(default_factory=list)
    current_item_id: str = ""
    completed_item_ids: list[str] = Field(default_factory=list)
    failed_item_ids: list[str] = Field(default_factory=list)
    blocked_item_ids: list[str] = Field(default_factory=list)
    skipped_item_ids: list[str] = Field(default_factory=list)
    pool_approval_id: str = ""
    linked_requirement_id: str = ""
    linked_plan_id: str = ""
    linked_autopilot_id: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)

    def item_ids(self) -> list[str]:
        return [item.item_id for item in self.items]

    def get_ready_items(self) -> list[AtlasPlanItem]:
        completed = set(self.completed_item_ids)
        unavailable = completed | set(self.failed_item_ids) | set(self.blocked_item_ids) | set(self.skipped_item_ids)
        return [
            item
            for item in self.items
            if item.status == "ready"
            and item.item_id not in unavailable
            and all(dependency_id in completed for dependency_id in item.depends_on)
        ]

    def get_item(self, item_id: str) -> AtlasPlanItem | None:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None


class AtlasPlanPoolSummary(BaseModel):
    pool_id: str
    root_goal: str
    status: AtlasPlanPoolStatus = "draft"
    total_items: int = 0
    completed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    current_item_id: str = ""
    planning_depth: AtlasPlanningDepth = "standard"
    automation_level: AtlasAutomationLevel = "plan_then_ask"
    execution_strategy: AtlasExecutionStrategy = "sequential"
