"""Policy taxonomies used to configure Forge methods independently of routes."""
from __future__ import annotations

from enum import StrEnum


class TaskDecompositionPolicy(StrEnum):
    NONE = "none"
    LIGHT = "light"
    NARROW_SLICE = "narrow_slice"
    MICRO_PATCH_ONLY = "micro_patch_only"
    ONE_ANCHOR_AT_A_TIME = "one_anchor_at_a_time"
    # PR18: finer-grained weak-model decomposition strategies.
    ONE_FAILURE_AT_A_TIME = "one_failure_at_a_time"
    TEST_FIRST_SLICE = "test_first_slice"
    CONTRACT_FIRST_SLICE = "contract_first_slice"
    ONE_FILE_ONE_CHANGE = "one_file_one_change"
    ONE_CONTRACT_ONE_PATCH = "one_contract_one_patch"


class InstructionAbstractionLevel(StrEnum):
    OUTCOME_ONLY = "outcome_only"
    CONCRETE_STEPS = "concrete_steps"
    EXPLICIT_TEMPLATE = "explicit_template"
    # PR18: graded abstraction for weak models (more guidance toward yes/no gating).
    GUIDED_GOAL = "guided_goal"
    CHECKLIST_STEPS = "checklist_steps"
    FILL_IN_TEMPLATE = "fill_in_template"
    CONSTRAINED_SLOTS = "constrained_slots"
    YES_NO_GATE = "yes_no_gate"


class ContextPackageMode(StrEnum):
    MINIMAL = "minimal"
    TWIN_BRIEF = "twin_brief"
    IMPACT_SLICE = "impact_slice"
    FULL_CONTEXT = "full_context"


class OutputProtocol(StrEnum):
    STRUCTURED_JSON = "structured_json"
    PATCH_DSL_JSON = "patch_dsl_json"
    EDIT_INTENT_LIST = "edit_intent_list"
    ANCHORED_EDIT_BLOCK = "anchored_edit_block"
    UNIFIED_DIFF = "unified_diff"
    FREEFORM_TEXT = "freeform_text"


class PatchConstructionMode(StrEnum):
    MODEL_GENERATED = "model_generated"
    DETERMINISTIC_TEXT = "deterministic_text"
    DETERMINISTIC_AST = "deterministic_ast"
    NONE = "none"


class VerificationMode(StrEnum):
    CONTRACT_ONLY = "contract_only"
    FOCUSED_TESTS = "focused_tests"
    AFFECTED_TESTS = "affected_tests"
    FULL_GATE = "full_gate"


class RepairMode(StrEnum):
    NONE = "none"
    RETRY = "retry"
    FALLBACK_METHOD = "fallback_method"
    REPAIR_COMPASS = "repair_compass"
    HUMAN_REVIEW = "human_review"
