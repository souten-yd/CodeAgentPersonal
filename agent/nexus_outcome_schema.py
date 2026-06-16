from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


def _new_outcome_id() -> str:
    return f"atlas_nexus_outcome_{uuid4().hex}"


AtlasOutcomeType = Literal[
    "success",
    "failure",
    "warning",
    "debug_lesson",
    "research_context",
    "verification_result",
    "safe_apply_result",
    "pipeline_summary",
]

AtlasOutcomeSource = Literal[
    "pipeline",
    "debug_loop",
    "safe_apply",
    "research",
    "verification",
    "manual",
]

AtlasOutcomeStatus = Literal[
    "pending",
    "saved",
    "saved_with_warnings",
    "skipped",
    "failed",
]


class AtlasNexusOutcome(BaseModel):
    outcome_id: str = Field(default_factory=_new_outcome_id)
    outcome_type: AtlasOutcomeType
    source: AtlasOutcomeSource
    status: AtlasOutcomeStatus = "pending"
    project: str = "CodeAgentPersonal"
    pool_id: str = ""
    item_id: str = ""
    run_id: str = ""
    title: str
    summary: str = ""
    root_cause: str = ""
    solution: str = ""
    reusable_lesson: str = ""
    related_files: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reusable: bool = True
    context_pack_id: str = ""
    debug_attempt_id: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AtlasNexusOutcomeWriteResult(BaseModel):
    outcome_id: str
    status: AtlasOutcomeStatus
    nexus_saved: bool = False
    journal_saved: bool = False
    nexus_record_id: str = ""
    json_path: str = ""
    markdown_path: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
