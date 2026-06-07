"""JSON Schemas used to constrain local-LLM (llama-server) structured output.

These are intentionally small and shallow: a weak local model (Gemma-4B) is far more reliable with
flat schemas and a handful of required fields than with deeply nested / strict-everything schemas.
They are passed to the adapter via ``call_llm_json(..., json_schema=...)`` which both sends them to
llama-server (json_schema / grammar constrained decoding) and injects them into the prompt as a hint.
"""
from __future__ import annotations

RISK_LEVELS = ["low", "medium", "high", "critical"]
PLAN_ACTION_TYPES = ["create", "update", "delete", "inspect", "run_command", "test"]


FILE_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "change_id": {"type": "string"},
        "path": {"type": "string"},
        "action_type": {"type": "string", "enum": ["create", "update"]},
        "content_mode": {"type": "string", "enum": ["full_content", "unified_diff", "edits", "append"]},
        "proposed_content": {"type": "string"},
        "patch": {"type": "string"},
        "unified_diff_preview": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"old_string": {"type": "string"}, "new_string": {"type": "string"}},
                "required": ["old_string", "new_string"],
                "additionalProperties": True,
            },
        },
        "append_content": {"type": "string"},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "required": ["path", "action_type"],
    "additionalProperties": True,
}


def patch_proposal_json_schema(*, require_content: bool = False) -> dict:
    """Schema for a single patch proposal.

    A valid applicable proposal may carry EITHER a full ``proposed_content`` OR a list of surgical
    ``edits`` (old->new). The schema stays permissive (nothing hard-required) because forcing one field
    would block the other path; the service enforces "some applicable content" and reports honestly when
    there is none. ``require_content`` is accepted for backward-compat and no longer changes the schema.
    """
    _ = require_content
    properties = {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "root_cause": {"type": "string"},
        "proposed_fix": {"type": "string"},
        "target_files": {"type": "array", "items": {"type": "string"}},
        "file_changes": {"type": "array", "items": FILE_CHANGE_SCHEMA},
        "proposed_content": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"old_string": {"type": "string"}, "new_string": {"type": "string"}},
                "required": ["old_string", "new_string"],
                "additionalProperties": True,
            },
        },
        "unified_diff_preview": {"type": "string"},
        "risk_level": {"type": "string", "enum": RISK_LEVELS},
        "satisfied_requirement_ids": {"type": "array", "items": {"type": "string"}},
        "preserved_requirement_ids": {"type": "array", "items": {"type": "string"}},
        "implemented_symbols": {"type": "array", "items": {"type": "string"}},
        "behavioral_cases": {"type": "array", "items": {"type": "string"}},
        "verification_cases": {"type": "array", "items": {"type": "string"}},
        "known_limitations": {"type": "array", "items": {"type": "string"}},
        "remaining_todos": {"type": "array", "items": {"type": "string"}},
    }
    # Do not hard-require proposed_content even when content is required: a surgical "edits" response is
    # equally valid. The service enforces "some applicable content" downstream (and reports honestly when
    # there is none), so we keep the schema permissive to avoid blocking the edits path.
    return {
        "type": "object",
        "properties": properties,
        "required": [],
        # Keep True: the service filters to its own allow-list anyway, and additionalProperties=false
        # is a common trigger for token-repetition collapse on weak models.
        "additionalProperties": True,
    }


def requirement_analysis_json_schema() -> dict:
    """Schema for the requirement analyzer's output.

    Shallow and fully optional: the analyzer normalizes messy scores/labels and coerces list-ish fields
    downstream, so the value here is steering a capable server into syntactically valid, on-shape JSON.
    """
    str_list = {"type": "array", "items": {"type": "string"}}
    properties = {
        "interpreted_goal": {"type": "string"},
        "user_intent": {"type": "string"},
        "task_type": {"type": "string"},
        "scope": str_list,
        "out_of_scope": str_list,
        "functional_requirements": str_list,
        "requirements": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "non_functional_requirements": str_list,
        "constraints": str_list,
        "acceptance_criteria": str_list,
        "verification_contract": {"type": "object", "additionalProperties": True},
        "expected_changes": str_list,
        "preserve_behaviors": str_list,
        "selected_architecture": {"type": "string"},
        "assumptions": str_list,
        "open_questions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "requirement_completeness_score": {"type": "number"},
        "category_scores": {"type": "object", "additionalProperties": True},
        "priority": {"type": "string"},
        "done_definition": str_list,
        "risks": str_list,
    }
    return {"type": "object", "properties": properties, "required": [], "additionalProperties": True}


def deep_plan_json_schema() -> dict:
    """Schema for the deep planner's three-option output."""
    str_list = {"type": "array", "items": {"type": "string"}}
    option = {
        "type": "object",
        "properties": {
            "option_id": {"type": "string", "enum": ["A", "B", "C"]},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "scope": str_list,
            "benefits": str_list,
            "drawbacks": str_list,
            "risk_level": {"type": "string", "enum": RISK_LEVELS},
            "estimated_complexity": {"type": "string"},
            "target_files": str_list,
            "why_selected": {"type": "string"},
            "why_rejected": {"type": "string"},
        },
        "required": ["option_id"],
        "additionalProperties": True,
    }
    properties = {
        "user_goal": {"type": "string"},
        "requirement_summary": {"type": "string"},
        "architecture_options": {"type": "array", "items": option},
        "selected_option_id": {"type": "string", "enum": ["A", "B", "C"]},
        "reflection": {"type": "object", "additionalProperties": True},
        "implementation_phases": str_list,
        "verification_strategy": str_list,
        "done_definition": str_list,
    }
    return {"type": "object", "properties": properties, "required": [], "additionalProperties": True}


def plan_generation_json_schema() -> dict:
    """Schema for the planner's implementation_steps output."""
    step = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "goal": {"type": "string"},
            "requirement_ids": {"type": "array", "items": {"type": "string"}},
            "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
            "target_files": {"type": "array", "items": {"type": "string"}},
            "file_changes": {"type": "array", "items": FILE_CHANGE_SCHEMA},
            "expected_changes": {"type": "array", "items": {"type": "string"}},
            "action_type": {"type": "string", "enum": PLAN_ACTION_TYPES},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "verification": {"type": "string"},
            "verification_contract": {"type": "object", "additionalProperties": True},
            "rollback": {"type": "string"},
            "preserve_behaviors": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "description", "goal", "acceptance_criteria", "action_type", "target_files"],
        "additionalProperties": True,
    }
    properties = {
        "user_goal": {"type": "string"},
        "original_user_request": {"type": "string"},
        "requirement_summary": {"type": "string"},
        "requirements": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "selected_architecture": {"type": "string"},
        "preserve_behaviors": {"type": "array", "items": {"type": "string"}},
        "implementation_steps": {"type": "array", "items": step},
        "target_files": {"type": "array", "items": {"type": "string"}},
        "test_plan": {"type": "array", "items": {"type": "string"}},
        "verification_plan": {"type": "array", "items": {"type": "string"}},
        "rollback_plan": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["implementation_steps", "test_plan", "rollback_plan"],
        "additionalProperties": True,
    }
