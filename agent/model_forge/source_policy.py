"""Forge source and privacy policy taxonomy (PFG-5).

Source modes control whether external/frontier providers may be used at all; privacy
modes control how much source context may leave the machine. Pure enum/helper code —
no provider calls. Local Only must block all external providers; the most restrictive
privacy mode (no_external_code) is the safe default for unlisted stages.
"""
from __future__ import annotations

from enum import StrEnum

from agent.model_forge.stage_taxonomy import ForgeStage


class SourceMode(StrEnum):
    LOCAL_ONLY = "local_only"
    LOCAL_PREFERRED = "local_preferred"
    HYBRID = "hybrid"
    FRONTIER_PREFERRED = "frontier_preferred"
    FRONTIER_ONLY = "frontier_only"


class PrivacyMode(StrEnum):
    NO_EXTERNAL_CODE = "no_external_code"
    SYMBOL_SUMMARY_ONLY = "symbol_summary_only"
    REDACTED_ONLY = "redacted_only"
    FULL_SOURCE_ALLOWED = "full_source_allowed"


# Least -> most source exposure. "Raising" a policy moves right (shares more).
_PRIVACY_ORDER: tuple[PrivacyMode, ...] = (
    PrivacyMode.NO_EXTERNAL_CODE,
    PrivacyMode.SYMBOL_SUMMARY_ONLY,
    PrivacyMode.REDACTED_ONLY,
    PrivacyMode.FULL_SOURCE_ALLOWED,
)

_DEFAULT_STAGE_PRIVACY: dict[ForgeStage, PrivacyMode] = {
    ForgeStage.REQUIREMENT_ANALYSIS: PrivacyMode.SYMBOL_SUMMARY_ONLY,
    ForgeStage.PLANNING: PrivacyMode.SYMBOL_SUMMARY_ONLY,
    ForgeStage.BLUEPRINT: PrivacyMode.REDACTED_ONLY,
    ForgeStage.CONTEXT_SELECTION: PrivacyMode.NO_EXTERNAL_CODE,
    ForgeStage.PATCH_GENERATION: PrivacyMode.NO_EXTERNAL_CODE,
    ForgeStage.TEST_GENERATION: PrivacyMode.NO_EXTERNAL_CODE,
    ForgeStage.FAILURE_CLASSIFICATION: PrivacyMode.REDACTED_ONLY,
    ForgeStage.REPAIR: PrivacyMode.NO_EXTERNAL_CODE,
    ForgeStage.REVIEW: PrivacyMode.REDACTED_ONLY,
    ForgeStage.FINAL_SUMMARY: PrivacyMode.SYMBOL_SUMMARY_ONLY,
}


def all_source_modes() -> list[SourceMode]:
    return list(SourceMode)


def all_privacy_modes() -> list[PrivacyMode]:
    return list(PrivacyMode)


def is_valid_source_mode(value: object) -> bool:
    try:
        SourceMode(value)  # type: ignore[arg-type]
        return True
    except ValueError:
        return False


def is_valid_privacy_mode(value: object) -> bool:
    try:
        PrivacyMode(value)  # type: ignore[arg-type]
        return True
    except ValueError:
        return False


def allows_external_providers(source_mode: SourceMode | str) -> bool:
    """Local Only blocks every external/frontier provider; all other modes may use them."""
    return SourceMode(source_mode) != SourceMode.LOCAL_ONLY


def default_privacy_for_stage(stage: ForgeStage | str) -> PrivacyMode:
    """Default external-sharing policy for a stage; unlisted stages get the most
    restrictive mode so context is never shared by accident."""
    return _DEFAULT_STAGE_PRIVACY.get(ForgeStage(stage), PrivacyMode.NO_EXTERNAL_CODE)


def privacy_rank(mode: PrivacyMode | str) -> int:
    return _PRIVACY_ORDER.index(PrivacyMode(mode))


def is_privacy_raise(current: PrivacyMode | str, requested: PrivacyMode | str) -> bool:
    """True when requested shares strictly more source context than current (a 'raise')."""
    return privacy_rank(requested) > privacy_rank(current)
