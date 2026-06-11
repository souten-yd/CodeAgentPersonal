"""Forge stage taxonomy (PFG-5).

Pure taxonomy/enum code: stable stage IDs, stage execution modes, and the default
rollout. No provider execution, no external calls, no production routing change.
"""
from __future__ import annotations

from enum import StrEnum


class ForgeStage(StrEnum):
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    CHANGE_CLASSIFICATION = "change_classification"
    PLANNING = "planning"
    BLUEPRINT = "blueprint"
    CONTEXT_SELECTION = "context_selection"
    PATCH_GENERATION = "patch_generation"
    TEST_GENERATION = "test_generation"
    FAILURE_CLASSIFICATION = "failure_classification"
    REPAIR = "repair"
    REVIEW = "review"
    VERIFICATION_INTERPRETATION = "verification_interpretation"
    CONVERGENCE_DECISION = "convergence_decision"
    FINAL_SUMMARY = "final_summary"


class StageMode(StrEnum):
    DISABLED = "disabled"
    FIXED_MODEL = "fixed_model"
    SHADOW_SELECT = "shadow_select"
    AUTO_SELECT = "auto_select"
    ARENA_SELECT = "arena_select"
    FALLBACK_ONLY = "fallback_only"


# Default rollout. Forge stays off for production routing: shadow_select observes and
# compares without changing the live output; everything else defaults to disabled.
# Cutover to auto_select / arena_select requires evidence (enforced in later packages).
_DEFAULT_STAGE_MODES: dict[ForgeStage, StageMode] = {
    ForgeStage.PLANNING: StageMode.SHADOW_SELECT,
    ForgeStage.PATCH_GENERATION: StageMode.SHADOW_SELECT,
    ForgeStage.FAILURE_CLASSIFICATION: StageMode.SHADOW_SELECT,
    ForgeStage.REPAIR: StageMode.SHADOW_SELECT,
    ForgeStage.REVIEW: StageMode.SHADOW_SELECT,
    ForgeStage.FINAL_SUMMARY: StageMode.DISABLED,
}

# Modes that change live production routing — none are defaults; reaching them is gated.
ACTIVE_PRODUCTION_MODES: frozenset[StageMode] = frozenset(
    {StageMode.FIXED_MODEL, StageMode.AUTO_SELECT, StageMode.ARENA_SELECT}
)


def all_stages() -> list[ForgeStage]:
    return list(ForgeStage)


def all_stage_modes() -> list[StageMode]:
    return list(StageMode)


def is_valid_stage(value: object) -> bool:
    try:
        ForgeStage(value)  # type: ignore[arg-type]
        return True
    except ValueError:
        return False


def is_valid_stage_mode(value: object) -> bool:
    try:
        StageMode(value)  # type: ignore[arg-type]
        return True
    except ValueError:
        return False


def default_stage_mode(stage: ForgeStage | str) -> StageMode:
    """Default execution mode for a stage. Unlisted stages default to disabled so
    Forge never affects production routing without an explicit, evidence-gated change."""
    return _DEFAULT_STAGE_MODES.get(ForgeStage(stage), StageMode.DISABLED)


def changes_production_routing(mode: StageMode | str) -> bool:
    return StageMode(mode) in ACTIVE_PRODUCTION_MODES
