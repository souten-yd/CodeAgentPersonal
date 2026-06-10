"""Digital Twin lifecycle and readiness (PI-4).

Determines twin readiness (absent/building/ready/stale/degraded/corrupt/disabled) from the
current project identity, the last recorded build, an integrity signal and the rollout
state, and decides whether a full build or an incremental refresh is required.

Pure decision logic plus a thin assembler that returns the public ``TwinProjectState`` DTO.
No persistence is performed here; the caller injects the last build record and integrity
status (so the twin's private store stays internal to the module).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.project_intelligence.contracts import (
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
    ProjectIdentity,
)
from agent.project_twin.facade import TwinProjectState, TwinReadiness


@dataclass(frozen=True)
class LastBuildRecord:
    """What the store knows about the most recent successful twin build."""

    twin_revision_id: str
    source_revision: str | None
    working_tree_hash: str
    parser_versions: dict[str, str] = field(default_factory=dict)


# Refresh decisions.
FULL_BUILD = "full_build"
INCREMENTAL_REFRESH = "incremental_refresh"
NO_REFRESH = "none"


def evaluate_readiness(
    identity: ProjectIdentity,
    last_build: LastBuildRecord | None,
    *,
    disabled: bool = False,
    integrity_status: str = "ok",
    building: bool = False,
    current_parser_versions: dict[str, str] | None = None,
    degraded_reasons: list[str] | None = None,
) -> tuple[TwinReadiness, list[str]]:
    """Return (readiness, stale_reasons). Fail closed on corruption."""
    if disabled:
        return TwinReadiness.DISABLED, []
    if integrity_status == "corrupt":
        return TwinReadiness.CORRUPT, ["store_corrupt"]
    if building:
        return TwinReadiness.BUILDING, []
    if last_build is None:
        return TwinReadiness.ABSENT, []

    stale: list[str] = []
    current_parsers = current_parser_versions or last_build.parser_versions
    if current_parsers != last_build.parser_versions:
        stale.append("parser_version_changed")
    if identity.source_revision != last_build.source_revision:
        stale.append("source_revision_changed")
    if identity.working_tree_hash != last_build.working_tree_hash:
        stale.append("working_tree_changed")

    if stale:
        return TwinReadiness.STALE, stale
    if degraded_reasons:
        return TwinReadiness.DEGRADED, list(degraded_reasons)
    return TwinReadiness.READY, []


def decide_refresh(readiness: TwinReadiness) -> str:
    """Choose the minimal valid build action for a readiness state."""
    if readiness in (TwinReadiness.ABSENT, TwinReadiness.CORRUPT):
        return FULL_BUILD  # corrupt fails closed then rebuilds
    if readiness in (TwinReadiness.STALE, TwinReadiness.DEGRADED):
        return INCREMENTAL_REFRESH
    return NO_REFRESH


def build_project_state(
    identity: ProjectIdentity,
    last_build: LastBuildRecord | None,
    *,
    disabled: bool = False,
    integrity_status: str = "ok",
    building: bool = False,
    current_parser_versions: dict[str, str] | None = None,
    degraded_reasons: list[str] | None = None,
    available_capabilities: list[str] | None = None,
) -> TwinProjectState:
    """Assemble the public TwinProjectState for the current lifecycle evaluation."""
    readiness, stale = evaluate_readiness(
        identity, last_build,
        disabled=disabled, integrity_status=integrity_status, building=building,
        current_parser_versions=current_parser_versions, degraded_reasons=degraded_reasons,
    )
    diagnostics: list[IntelligenceDiagnostic] = []
    if readiness == TwinReadiness.CORRUPT:
        diagnostics.append(IntelligenceDiagnostic(
            code=IntelligenceErrorCode.STORE_CORRUPT,
            message="twin store integrity check failed; rebuild required",
            severity="error",
        ))
    return TwinProjectState(
        project=identity,
        readiness=readiness,
        twin_revision_id=last_build.twin_revision_id if last_build else None,
        parser_versions=dict(current_parser_versions or (last_build.parser_versions if last_build else {})),
        available_capabilities=list(available_capabilities or []),
        stale_reasons=stale,
        diagnostics=diagnostics,
    )
