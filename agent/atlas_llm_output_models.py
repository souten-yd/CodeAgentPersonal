"""Pydantic models describing the *expected shape* of structured LLM outputs.

These are deliberately distinct from the domain models (``Plan``, ``RequirementDefinition`` …): they
validate the raw JSON a local model emits, not the assembled-with-defaults domain object. They are the
backend-authoritative check that the proposal calls for — a JSON-schema / GBNF constraint only buys us
*syntactic* shape, so after generation we validate with Pydantic and retry on failure.

Design rules
------------
- Stay permissive (``extra="ignore"``) so a model adding helpful extra keys never triggers a retry.
- Type only what is genuinely load-bearing. Fields the downstream code already coerces (``_as_str_list``,
  ``_score`` …) are typed ``Any`` so a recoverable mess does not cause a wasteful retry.
- The one place with real teeth is the planner: an empty / missing ``implementation_steps`` is exactly the
  failure that strands patch generation at ``0/N``, so it is required + non-empty and therefore retried.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _PermissiveModel(BaseModel):
    # Local models routinely emit extra keys; ignoring them keeps validation about shape, not noise.
    model_config = ConfigDict(extra="ignore")


# ── Requirement analysis (PR-2) ───────────────────────────────────────────────────────────────────
# The analyzer already normalizes messy scores/labels and coerces list-ish fields, so the validation
# win here is the schema-constrained decoding it now goes through, not field-level enforcement.
class RequirementAnalysisOutput(_PermissiveModel):
    interpreted_goal: Any = None
    user_intent: Any = None
    task_type: Any = None
    scope: Any = None
    out_of_scope: Any = None
    functional_requirements: Any = None
    non_functional_requirements: Any = None
    constraints: Any = None
    assumptions: Any = None
    open_questions: Any = None
    requirement_completeness_score: Any = None
    category_scores: Any = None
    priority: Any = None
    done_definition: Any = None
    risks: Any = None


# ── Plan generation (PR-3) ────────────────────────────────────────────────────────────────────────
class PlanStepOutput(_PermissiveModel):
    title: Any = None
    description: Any = None
    goal: Any = None
    acceptance_criteria: Any = None
    target_files: Any = None
    file_changes: Any = None
    action_type: Any = None
    risk_level: Any = None
    verification: Any = None
    rollback: Any = None


class PlanGenerationOutput(_PermissiveModel):
    # Required + non-empty: a plan with no steps produces no patch items, which is precisely the
    # "Patch generation has not started (0/N)" stall. Failing validation here triggers a bounded retry
    # before the planner falls back, giving a weak model a second chance to emit real steps.
    implementation_steps: list[PlanStepOutput] = Field(min_length=1)
    user_goal: Any = None
    requirement_summary: Any = None
    selected_architecture: Any = None
    architecture_options: Any = None
    rejected_architectures: Any = None
    assumptions: Any = None
    constraints: Any = None
    target_files: Any = None
    expected_file_changes: Any = None
    test_plan: Any = None
    verification_plan: Any = None
    rollback_plan: Any = None
    risks: Any = None
    done_definition: Any = None


# ── Deep planning (PR-3) ──────────────────────────────────────────────────────────────────────────
# Deep planner always rebuilds three options with defaults, so this just confirms object shape and lets
# the deep plan go through schema-constrained decoding it previously bypassed.
class DeepPlanOutput(_PermissiveModel):
    user_goal: Any = None
    requirement_summary: Any = None
    architecture_options: Any = None
    selected_option_id: Any = None
    reflection: Any = None
    implementation_phases: Any = None
    verification_strategy: Any = None
    done_definition: Any = None


# ── Adversarial critique / plan-reviewer findings (PR-1) ────────────────────────────────────────────
class CritiqueFindingOutput(_PermissiveModel):
    angle: Any = None
    severity: Any = None
    category: Any = None
    title: Any = None
    detail: Any = None
    recommendation: Any = None


class AdversarialCritiqueOutput(_PermissiveModel):
    # Empty findings is a legitimate "no issues" result, so findings is not required — only its type is
    # validated (a non-list findings value is broken and is retried).
    findings: list[CritiqueFindingOutput] = Field(default_factory=list)
    angle_risk: Any = None
    requires_revision: Any = None
