from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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
    "waiting_for_critical_decision",
    "blocked_safety_review",
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
    "needs_scope_confirmation",
    "ready",
    "approval_required",
    "waiting_for_critical_decision",
    # A post-clarification apply-time safety block the user can exit via override / revise / cancel
    # (distinct from the terminal "blocked"); see AtlasClarificationReplanningService._next_status.
    "blocked_safety_review",
    "approved",
    "running",
    "paused",
    "waiting",
    "dependency_waiting",
    "needs_revision",
    "completed",
    "completed_with_warnings",
    "failed",
    "blocked",
    "blocked_safety_review",
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
    acceptance_criteria: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    verification_contract: dict[str, Any] = Field(default_factory=dict)
    preserve_behaviors: list[str] = Field(default_factory=list)
    original_user_request: str = ""
    selected_architecture: str = ""
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
    original_user_request: str = ""
    selected_architecture: str = ""
    global_constraints: list[str] = Field(default_factory=list)
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    preserve_behaviors: list[str] = Field(default_factory=list)
    requirement_item_map: dict[str, list[str]] = Field(default_factory=dict)
    plan_quality: dict[str, Any] = Field(default_factory=dict)
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

    def _dependency_aliases(self, item: AtlasPlanItem, index: int) -> set[str]:
        aliases = {item.item_id, f"step_{index}", f"item_{index}"}
        step_id = str(getattr(item, "metadata", {}).get("step_id") or "").strip()
        if step_id:
            aliases.add(step_id)
        item_step_id = str(getattr(item, "metadata", {}).get("item_step_id") or "").strip()
        if item_step_id:
            aliases.add(item_step_id)
        return {a for a in aliases if a}

    def get_ready_items(self) -> list[AtlasPlanItem]:
        completed = set(self.completed_item_ids)
        completed_aliases: set[str] = set(completed)
        for idx, item in enumerate(self.items, start=1):
            if item.item_id in completed or item.status in {"completed", "skipped"}:
                completed_aliases.update(self._dependency_aliases(item, idx))

        unavailable = completed | set(self.failed_item_ids) | set(self.blocked_item_ids) | set(self.skipped_item_ids)
        ready_items: list[AtlasPlanItem] = []
        for item in self.items:
            if item.item_id in unavailable:
                continue
            dependencies_satisfied = all(dependency_id in completed_aliases for dependency_id in item.depends_on)
            if not dependencies_satisfied:
                continue
            if item.status == "ready":
                ready_items.append(item)
                continue
            if item.status == "queued" and item.depends_on:
                ready_items.append(item)
        return ready_items

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
