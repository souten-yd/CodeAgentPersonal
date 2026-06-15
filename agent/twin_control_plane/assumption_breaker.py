"""Assumption Breaker brief generator."""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.no_data_bootstrap_gate import NoDataBootstrapAssessment
from agent.twin_control_plane.schema_guardian import SchemaGuardianReport
from agent.twin_control_plane.state_mirror import StateMirrorReport
from agent.twin_control_plane.twinproof import TwinProofReport
from agent.twin_control_plane.contracts import TwinControlPlaneModel


class AssumptionBreakerCase(StrEnum):
    NO_DATA = "no_data"
    RELOAD = "reload"
    PERSISTENCE = "persistence"
    UI_PROJECTION = "ui_projection"
    FEATURE_FLAG = "feature_flag"
    STALE_CONTRACT = "stale_contract"
    SCHEMA = "schema"


class AssumptionBreakerBrief(TwinControlPlaneModel):
    brief_id: str = Field(min_length=1)
    case_type: AssumptionBreakerCase
    prompt: str = Field(min_length=1)
    refs: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def generate_assumption_breaker_briefs(
    twinproof: TwinProofReport,
    *,
    no_data: NoDataBootstrapAssessment | None = None,
    schema_guardian: SchemaGuardianReport | None = None,
    state_mirror: StateMirrorReport | None = None,
    feature_flag_refs: Iterable[str] = (),
    stale_contract_refs: Iterable[str] = (),
) -> list[AssumptionBreakerBrief]:
    """Generate targeted briefs for assumptions that need adversarial proof."""
    briefs: list[AssumptionBreakerBrief] = []

    if no_data and no_data.bootstrap_required:
        briefs.append(AssumptionBreakerBrief(
            brief_id="assumption_breaker:no_data",
            case_type=AssumptionBreakerCase.NO_DATA,
            prompt="Assume no initial files, data, runtime evidence, or tests exist. Identify bootstrap proof before implementation.",
            refs=[req.requirement_id for req in no_data.requirements],
            proof_requirements=[req.proof_requirement for req in no_data.requirements],
        ))

    if schema_guardian and schema_guardian.findings:
        briefs.append(AssumptionBreakerBrief(
            brief_id="assumption_breaker:schema",
            case_type=AssumptionBreakerCase.SCHEMA,
            prompt="Assume unit tests are insufficient for schema drift. Identify compatibility, migration, and consumer proof.",
            refs=[finding.finding_id for finding in schema_guardian.findings],
            proof_requirements=list(schema_guardian.proof_requirements),
        ))

    if state_mirror:
        reload_refs = [finding.path for finding in state_mirror.findings if "reload" in " ".join(finding.proof_requirements).lower() or "completed_plan_item_count" in finding.path]
        persistence_refs = [finding.path for finding in state_mirror.findings if "persistence" in finding.path or "persisted" in finding.message.lower()]
        ui_refs = [finding.path for finding in state_mirror.findings if any(surface.value == "ui_projection" for surface in finding.surfaces)]
        if reload_refs:
            briefs.append(AssumptionBreakerBrief(
                brief_id="assumption_breaker:reload",
                case_type=AssumptionBreakerCase.RELOAD,
                prompt="Assume reload loses state. Prove plan revision and completed counts survive restart/reload.",
                refs=_unique(reload_refs),
                proof_requirements=[req for finding in state_mirror.findings for req in finding.proof_requirements],
            ))
        if persistence_refs:
            briefs.append(AssumptionBreakerBrief(
                brief_id="assumption_breaker:persistence",
                case_type=AssumptionBreakerCase.PERSISTENCE,
                prompt="Assume persisted artifact state diverges from runtime. Prove create/read/reload and runtime reconciliation.",
                refs=_unique(persistence_refs),
                proof_requirements=[req for finding in state_mirror.findings for req in finding.proof_requirements],
            ))
        if ui_refs:
            briefs.append(AssumptionBreakerBrief(
                brief_id="assumption_breaker:ui_projection",
                case_type=AssumptionBreakerCase.UI_PROJECTION,
                prompt="Assume UI controls can disagree with backend authority. Prove backend-to-UI projection and disabled controls.",
                refs=_unique(ui_refs),
                proof_requirements=[req for finding in state_mirror.findings for req in finding.proof_requirements],
            ))

    flags = _unique(feature_flag_refs)
    if flags:
        briefs.append(AssumptionBreakerBrief(
            brief_id="assumption_breaker:feature_flag",
            case_type=AssumptionBreakerCase.FEATURE_FLAG,
            prompt="Assume feature flag off-baseline is missing. Prove disabled/default behavior and enabled behavior separately.",
            refs=flags,
            proof_requirements=[f"Run feature flag off-baseline and enabled-path proof for {ref}." for ref in flags],
        ))

    stale = _unique([*stale_contract_refs, *twinproof.stale_candidates])
    if stale:
        briefs.append(AssumptionBreakerBrief(
            brief_id="assumption_breaker:stale_contract",
            case_type=AssumptionBreakerCase.STALE_CONTRACT,
            prompt="Assume stale tests/contracts are retirement candidates only. Do not delete or weaken without proof and approval.",
            refs=stale,
            proof_requirements=[f"Classify stale contract and record retirement proof for {ref}." for ref in stale],
        ))

    return sorted(briefs, key=lambda brief: brief.brief_id)


__all__ = ["AssumptionBreakerBrief", "AssumptionBreakerCase", "generate_assumption_breaker_briefs"]
