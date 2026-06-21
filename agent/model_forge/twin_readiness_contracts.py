from __future__ import annotations

from typing import Literal

from pydantic import Field

from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.schema import ForgeModel


class TwinReadinessRequest(ForgeModel):
    project_id: str = Field(min_length=1)
    project_path: str = Field(min_length=1)
    changed_refs: list[str] = Field(default_factory=list)
    task_category: str = "codegen"
    change_class: ChangeClass = ChangeClass.MEDIUM
    max_depth: int | None = Field(default=None, ge=0)
    budget: int = Field(default=60, ge=1)
    metadata: dict = Field(default_factory=dict)


class TwinReadinessSignal(ForgeModel):
    name: str
    status: Literal["passed", "failed", "unavailable", "warning"]
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    detail: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class TwinReadinessReport(ForgeModel):
    report_id: str
    project_id: str
    project_path: str
    overall_score: float | None = Field(default=None, ge=0.0, le=1.0)
    readiness_level: Literal["unavailable", "low", "medium", "high", "trusted"]
    signals: list[TwinReadinessSignal] = Field(default_factory=list)
    recommended_max_assist_mode: str = ""
    recommended_injection_cap: int | None = Field(default=None, ge=0, le=4)
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = ""
