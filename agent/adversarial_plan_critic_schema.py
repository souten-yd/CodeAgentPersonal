from __future__ import annotations

from pydantic import BaseModel, Field


class PlanCritiqueFinding(BaseModel):
    angle: str = ""
    severity: str = "info"  # info | warning | high | critical
    category: str = "other"
    title: str = ""
    detail: str = ""
    recommendation: str = ""


class AdversarialCritiqueResult(BaseModel):
    angles_evaluated: list[str] = Field(default_factory=list)
    findings: list[PlanCritiqueFinding] = Field(default_factory=list)
    consensus_risk: str = "low"  # low | medium | high | critical
    requires_revision: bool = False
    warnings: list[str] = Field(default_factory=list)
