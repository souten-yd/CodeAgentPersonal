"""Strict contracts for baseline-versus-assisted Forge evaluations."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.schema import ForgeModel
from agent.model_forge.source_policy import SourceMode
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode

TwinAssistStatus = Literal["passed", "failed", "unavailable", "blocked"]


class TwinAssistCase(ForgeModel):
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    task_category: str = "codegen"
    change_class: ChangeClass = ChangeClass.MEDIUM
    target_files: list[str] = Field(default_factory=list)
    project_fixture_id: str = ""
    user_goal: str = Field(min_length=1)
    expected_behavior: str = ""
    baseline_allowed: bool = True
    assist_modes: list[TwinAssistMode] = Field(default_factory=list)
    required_refs: list[str] = Field(default_factory=list)
    forbidden_refs: list[str] = Field(default_factory=list)
    expected_symbols: list[str] = Field(default_factory=list)
    expected_tests: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class TwinAssistRunRequest(ForgeModel):
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    base_url: str = "http://127.0.0.1:8080"
    case_ids: list[str] = Field(default_factory=list)
    assist_modes: list[TwinAssistMode] = Field(default_factory=list)
    run_baseline: bool = True
    project_fixture_root: str = "ca_data/model_forge/twin_assist_fixtures"
    timeout_seconds: float = Field(default=120.0, gt=0)
    source_mode: SourceMode = SourceMode.LOCAL_ONLY
    privacy_sensitive: bool = True


class TwinAssistAttemptResult(ForgeModel):
    case_id: str = Field(min_length=1)
    assist_mode: TwinAssistMode
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    status: TwinAssistStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    patch_content_available: bool = False
    semantic_passed: bool = False
    verification_passed: bool = False
    touched_files: list[str] = Field(default_factory=list)
    forbidden_touched: list[str] = Field(default_factory=list)
    implemented_symbols: list[str] = Field(default_factory=list)
    verification_cases: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    raw_output_ref: str = ""
    proposal_ref: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    failed_reasons: list[str] = Field(default_factory=list)
    unavailable_reasons: list[str] = Field(default_factory=list)


class TwinAssistCaseComparison(ForgeModel):
    case_id: str = Field(min_length=1)
    baseline: TwinAssistAttemptResult | None = None
    assisted: list[TwinAssistAttemptResult] = Field(default_factory=list)
    best_assist_mode: TwinAssistMode | None = None
    best_score: float | None = Field(default=None, ge=0.0, le=1.0)
    lift: float | None = Field(default=None, ge=-1.0, le=1.0)
    harm_detected: bool = False
    recommendation: str = ""
    reasons: list[str] = Field(default_factory=list)


class TwinAssistEvaluationReport(ForgeModel):
    run_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    status: TwinAssistStatus
    comparisons: list[TwinAssistCaseComparison] = Field(default_factory=list)
    aggregate_scores: dict[str, float] = Field(default_factory=dict)
    recommended_twin_injection_level: int = Field(default=0, ge=0, le=4)
    recommended_assist_modes: list[TwinAssistMode] = Field(default_factory=list)
    recommended_method_overrides: dict[str, str] = Field(default_factory=dict)
    recommended_fallback_chain: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = ""
