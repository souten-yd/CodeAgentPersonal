from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceType = Literal[
    "memory",
    "skill",
    "skill_file",
    "past_requirement",
    "past_plan",
    "run_log",
    "project_file",
    "project_note",
    "nexus_evidence",
    "nexus_report",
    "other",
]
RiskLevel = Literal["low", "medium", "high"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NexusContextItem(BaseModel):
    item_id: str
    source_type: SourceType = "other"
    title: str = ""
    content: str = ""
    summary: str = ""
    source_path: str = ""
    source_id: str = ""
    score: float = 0.0
    reason: str = ""
    freshness: str = "unknown"
    risk_level: RiskLevel = "low"
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NexusContextPack(BaseModel):
    available: bool = False
    summary: str = ""
    items: list[NexusContextItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)
    total_items_before_filter: int = 0
    total_items_after_filter: int = 0
    context_budget_chars: int = 12000
    truncated: bool = False
    compact_text: str = ""
