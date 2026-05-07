from __future__ import annotations

from pydantic import BaseModel, Field


class DeepArchitectureOption(BaseModel):
    option_id: str
    title: str
    summary: str = ""
    scope: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    drawbacks: list[str] = Field(default_factory=list)
    risk_level: str = "medium"
    estimated_complexity: str = "medium"
    target_files: list[str] = Field(default_factory=list)
    why_selected: str = ""
    why_rejected: str = ""


class DeepPlanningReflection(BaseModel):
    nexus_context_used: str = ""
    repository_context_used: str = ""
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)


class DeepPlanPayload(BaseModel):
    requirement_id: str
    planning_mode: str = "deep_nexus"
    user_goal: str = ""
    requirement_summary: str = ""
    architecture_options: list[DeepArchitectureOption] = Field(default_factory=list)
    selected_option_id: str = "A"
    reflection: DeepPlanningReflection = Field(default_factory=DeepPlanningReflection)
    implementation_phases: list[str] = Field(default_factory=list)
    verification_strategy: list[str] = Field(default_factory=list)
    done_definition: list[str] = Field(default_factory=list)
