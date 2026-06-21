"""Stable method variants for Forge execution.

Routes describe the development path. Method variants independently describe the
output and patch construction protocol used within a route.
"""
from __future__ import annotations

from enum import StrEnum


class MethodVariant(StrEnum):
    STRUCTURED_PATCH_JSON = "structured_patch_json"
    PATCH_DSL_JSON = "patch_dsl_json"
    EDIT_INTENT_LIST = "edit_intent_list"
    ANCHORED_EDIT_BLOCK = "anchored_edit_block"
    UNIFIED_DIFF = "unified_diff"
    TOOL_CALL_PATCH = "tool_call_patch"
    DETERMINISTIC_TEXT_PATCH = "deterministic_text_patch"
    DETERMINISTIC_AST_PATCH = "deterministic_ast_patch"
    REVIEW_ONLY = "review_only"
    TEST_PLAN_ONLY = "test_plan_only"
    REPAIR_COMPASS_STEPS = "repair_compass_steps"
