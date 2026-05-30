"""JSON Schemas used to constrain local-LLM (llama-server) structured output.

These are intentionally small and shallow: a weak local model (Gemma-4B) is far more reliable with
flat schemas and a handful of required fields than with deeply nested / strict-everything schemas.
They are passed to the adapter via ``call_llm_json(..., json_schema=...)`` which both sends them to
llama-server (json_schema / grammar constrained decoding) and injects them into the prompt as a hint.
"""
from __future__ import annotations

RISK_LEVELS = ["low", "medium", "high", "critical"]
PLAN_ACTION_TYPES = ["create", "update", "delete", "inspect", "run_command", "test"]


def patch_proposal_json_schema(*, require_content: bool) -> dict:
    """Schema for a single patch proposal.

    When ``require_content`` is True (a plan_item that writes a target file), ``proposed_content`` is
    required so the model cannot return an applicable-looking proposal with no file body. For advisory
    sources (debug_review) nothing is hard-required.
    """
    properties = {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "root_cause": {"type": "string"},
        "proposed_fix": {"type": "string"},
        "target_files": {"type": "array", "items": {"type": "string"}},
        "proposed_content": {"type": "string"},
        "unified_diff_preview": {"type": "string"},
        "risk_level": {"type": "string", "enum": RISK_LEVELS},
    }
    required = ["proposed_content"] if require_content else []
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        # Keep True: the service filters to its own allow-list anyway, and additionalProperties=false
        # is a common trigger for token-repetition collapse on weak models.
        "additionalProperties": True,
    }


def plan_generation_json_schema() -> dict:
    """Schema for the planner's implementation_steps output."""
    step = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "target_files": {"type": "array", "items": {"type": "string"}},
            "action_type": {"type": "string", "enum": PLAN_ACTION_TYPES},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "verification": {"type": "string"},
            "rollback": {"type": "string"},
        },
        "required": ["title", "action_type"],
        "additionalProperties": True,
    }
    properties = {
        "user_goal": {"type": "string"},
        "requirement_summary": {"type": "string"},
        "selected_architecture": {"type": "string"},
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
        "required": ["implementation_steps"],
        "additionalProperties": True,
    }
