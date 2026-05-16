from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_research_request_id() -> str:
    return f"atlas_research_request_{uuid4().hex}"


def _new_context_finding_id() -> str:
    return f"atlas_context_finding_{uuid4().hex}"


def _new_context_pack_id() -> str:
    return f"atlas_context_pack_{uuid4().hex}"


AtlasResearchSource = Literal[
    "planner",
    "autopilot",
    "debug_loop",
    "recovery",
    "manual",
]

AtlasResearchPurpose = Literal[
    "codebase_context",
    "memory_context",
    "log_context",
    "web_research",
    "ui_design_research",
    "technical_research",
    "math_reasoning_support",
    "intent_disambiguation",
    "support_data_collection",
]

AtlasResearchDepth = Literal[
    "micro",
    "standard",
    "deep",
]

AtlasResearchStatus = Literal[
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
    "skipped",
]

AtlasContextFindingType = Literal[
    "memory",
    "log",
    "codebase",
    "skill",
    "design_pattern",
    "technical_spec",
    "math_support",
    "intent",
    "support_data",
    "warning",
    "other",
]


class AtlasNexusResearchRequest(BaseModel):
    request_id: str = Field(default_factory=_new_research_request_id)
    pool_id: str = ""
    item_id: str = ""
    run_id: str = ""
    source: AtlasResearchSource = "planner"
    purpose: AtlasResearchPurpose
    query: str
    project_path: str = ""
    project_name: str = ""
    depth: AtlasResearchDepth = "micro"
    constraints: list[str] = Field(default_factory=list)
    expected_output: str = "context_pack"
    max_queries: int = 5
    max_sources: int = 10
    max_time_seconds: int = 60
    allow_web: bool = False
    allow_deep_research: bool = False
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)


class AtlasContextFinding(BaseModel):
    finding_id: str = Field(default_factory=_new_context_finding_id)
    finding_type: AtlasContextFindingType = "other"
    title: str
    content: str = ""
    confidence: float = 0.0
    source_type: str = ""
    source_id: str = ""
    source_path: str = ""
    freshness: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasNexusContextPack(BaseModel):
    context_pack_id: str = Field(default_factory=_new_context_pack_id)
    request_id: str
    purpose: AtlasResearchPurpose
    status: AtlasResearchStatus = "completed"
    summary: str = ""
    findings: list[AtlasContextFinding] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    confidence: float = 0.0
    freshness: str = ""
    insufficient_context: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)
