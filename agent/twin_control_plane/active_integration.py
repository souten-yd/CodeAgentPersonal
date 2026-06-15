"""Atlas active integration behind a gate (TFG-11 / Package 11).

Drives the full Twin/Forge/Git Steward loop for one plan item — ExecutionPolicy ->
compiled instruction -> local Git branch prep -> generation -> Safe Apply -> post-apply
Twin refresh -> Patch Impact Gate -> TwinProof -> Proof Ledger -> Repair Compass — but
only when explicitly switched to ACTIVE, and only after shadow evidence exists.

Hard safety invariants, all enforced here:

- OFF is the default and is unchanged: ``run`` in OFF returns a no-op result and mutates
  nothing, so a caller that never opts in behaves exactly as the legacy flow;
- ACTIVE requires prior shadow evidence: without a SHADOW ``TwinShadowReport`` the run is
  BLOCKED and nothing is generated or applied;
- Safe Apply remains the only write boundary: this orchestrator never writes product
  files. It delegates application to a Safe Apply hook and BLOCKS if a hook reports a
  change that was applied without going through Safe Apply;
- remote publication is never performed: only local, Atlas-owned Git branch prep runs;
- active mode is reversible: it can be disabled by constructing with ``OFF`` (or via
  ``disabled``), with no residual global state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable

from pydantic import Field

from agent.git_steward.contracts import GitStewardResult
from agent.git_steward.local_adapter import detect_repository, prepare_branch
from agent.twin_control_plane.contracts import (
    ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION,
    ExecutionPolicy,
    TwinBrief,
    TwinControlPlaneModel,
)
from agent.twin_control_plane.instruction_compiler import CompiledInstruction, compile_model_instruction
from agent.twin_control_plane.patch_impact_gate import (
    PatchGateDecision,
    PatchImpactReport,
    VerificationEvidence,
    evaluate_patch_impact,
)
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry, create_proof_ledger_entry
from agent.twin_control_plane.repair_compass import RepairCompassReport, build_repair_compass
from agent.twin_control_plane.shadow_integration import TwinShadowMode, TwinShadowReport
from agent.twin_control_plane.twinproof import TwinProofReport


class PipelineMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"


class PipelineStatus(StrEnum):
    OFF = "off"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"
    NEEDS_REPAIR = "needs_repair"
    EXHAUSTED = "exhausted"
    SHADOW = "shadow"


class ProposalDraft(TwinControlPlaneModel):
    """Model generation output — a proposal, NOT an applied change."""

    proposal_id: str = Field(min_length=1)
    summary: str = ""
    changed_files: list[str] = Field(default_factory=list)
    raw_output_ref: str = ""


class ApplyOutcome(TwinControlPlaneModel):
    """Result of the delegated Safe Apply step. ``via_safe_apply`` must be True for any
    applied change; an applied change with ``via_safe_apply=False`` is a boundary
    violation and is blocked."""

    applied: bool = False
    via_safe_apply: bool = True
    changed_files: list[str] = Field(default_factory=list)
    commit_sha: str = ""
    reasons: list[str] = Field(default_factory=list)


class AttemptRecord(TwinControlPlaneModel):
    attempt: int
    proposal_id: str = ""
    applied: bool = False
    decision: str = ""
    patch_report_id: str = ""
    repair_report_id: str = ""
    reasons: list[str] = Field(default_factory=list)


class ActivePipelineResult(TwinControlPlaneModel):
    schema_version: str = ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION
    report_id: str = Field(min_length=1)
    mode: PipelineMode
    status: PipelineStatus
    requires_shadow_evidence: bool = False
    policy_id: str = ""
    brief_id: str = ""
    instruction_id: str = ""
    branch: str = ""
    base_ref: str = ""
    head_ref: str = ""
    attempts: list[AttemptRecord] = Field(default_factory=list)
    patch_report: PatchImpactReport | None = None
    ledger_entry: ProofLedgerEntry | None = None
    repair_reports: list[RepairCompassReport] = Field(default_factory=list)
    accepted: bool = False
    reasons: list[str] = Field(default_factory=list)


# Hook signatures — the Atlas pipeline owns how these are realised. Defaults are inert so
# the orchestrator is testable and never invents work.
GenerateHook = Callable[[CompiledInstruction, "RepairCompassReport | None"], ProposalDraft]
SafeApplyHook = Callable[[ProposalDraft], ApplyOutcome]
VerifyHook = Callable[[ProposalDraft, ApplyOutcome], list[VerificationEvidence]]
TwinRefreshHook = Callable[[ProposalDraft, ApplyOutcome], str]


@dataclass
class PipelineHooks:
    generate: GenerateHook
    # The Safe Apply boundary. The orchestrator never writes files itself.
    safe_apply: SafeApplyHook
    verify: VerifyHook = field(default=lambda proposal, apply: [])
    refresh_twin: TwinRefreshHook = field(default=lambda proposal, apply: "")


class ActiveIntegrationOrchestrator:
    """Gated, reversible active integration. Composes existing gates; delegates mutation."""

    def __init__(
        self,
        mode: PipelineMode = PipelineMode.OFF,
        *,
        disabled: bool = False,
        max_repair_attempts: int = 2,
    ) -> None:
        self._mode = PipelineMode(mode)
        self._disabled = bool(disabled)
        self._max_attempts = max(1, int(max_repair_attempts))

    @property
    def mode(self) -> PipelineMode:
        return PipelineMode.OFF if self._disabled else self._mode

    def _result(self, status: PipelineStatus, *, policy: ExecutionPolicy, brief: TwinBrief,
                instruction_id: str = "", **kw) -> ActivePipelineResult:
        return ActivePipelineResult(
            report_id=f"active_pipeline:{policy.policy_id}:{brief.brief_id}",
            mode=self.mode, status=status, policy_id=policy.policy_id,
            brief_id=brief.brief_id, instruction_id=instruction_id, **kw,
        )

    def run(
        self,
        *,
        policy: ExecutionPolicy,
        brief: TwinBrief,
        hooks: PipelineHooks,
        requirement_ref: str = "",
        plan_item_ref: str = "",
        repo_path: str | None = None,
        branch_name: str = "",
        before_twin_revision_id: str = "",
        shadow_report: TwinShadowReport | None = None,
        twinproof: TwinProofReport | None = None,
    ) -> ActivePipelineResult:
        # 1) OFF (or disabled): legacy unchanged, nothing generated/applied.
        if self.mode == PipelineMode.OFF:
            return self._result(PipelineStatus.OFF, policy=policy, brief=brief,
                                reasons=["pipeline_off"])

        instruction = compile_model_instruction(brief, policy)

        # 2) ACTIVE requires prior shadow evidence.
        if self.mode == PipelineMode.ACTIVE and not _has_shadow_evidence(shadow_report):
            return self._result(
                PipelineStatus.BLOCKED, policy=policy, brief=brief,
                instruction_id=instruction.instruction_id,
                requires_shadow_evidence=True,
                reasons=["active_requires_shadow_evidence"],
            )

        # 3) Local, Atlas-owned Git branch prep (never remote).
        branch = branch_name or f"atlas/{plan_item_ref or 'plan'}"
        base_ref = before_twin_revision_id
        git_result: GitStewardResult | None = None
        if repo_path and policy.git_policy.local_branch_required:
            state = detect_repository(repo_path)
            base_ref = base_ref or state.head_sha
            git_result = prepare_branch(repo_path, branch, require_clean=True)
            if git_result.status != "ok":
                return self._result(
                    PipelineStatus.BLOCKED, policy=policy, brief=brief,
                    instruction_id=instruction.instruction_id, branch=branch,
                    base_ref=base_ref,
                    reasons=["git_branch_prep_blocked", *git_result.reasons],
                )

        # SHADOW: dry run — generate a proposal as evidence but never apply.
        if self.mode == PipelineMode.SHADOW:
            proposal = hooks.generate(instruction, None)
            return self._result(
                PipelineStatus.SHADOW, policy=policy, brief=brief,
                instruction_id=instruction.instruction_id, branch=branch, base_ref=base_ref,
                attempts=[AttemptRecord(attempt=1, proposal_id=proposal.proposal_id,
                                        applied=False, decision="shadow",
                                        reasons=["shadow_dry_run_no_apply"])],
                reasons=["shadow_dry_run"],
            )

        # 4) ACTIVE repair loop.
        attempts: list[AttemptRecord] = []
        repair_reports: list[RepairCompassReport] = []
        last_repair: RepairCompassReport | None = None
        last_patch: PatchImpactReport | None = None
        last_ledger: ProofLedgerEntry | None = None

        for attempt in range(1, self._max_attempts + 1):
            proposal = hooks.generate(instruction, last_repair)
            apply_outcome = hooks.safe_apply(proposal)

            # Safe Apply boundary enforcement: an applied change that did not go through
            # Safe Apply is a hard boundary violation; block immediately.
            if apply_outcome.applied and not apply_outcome.via_safe_apply:
                attempts.append(AttemptRecord(
                    attempt=attempt, proposal_id=proposal.proposal_id, applied=True,
                    decision="blocked", reasons=["safe_apply_bypassed"],
                ))
                return self._result(
                    PipelineStatus.BLOCKED, policy=policy, brief=brief,
                    instruction_id=instruction.instruction_id, branch=branch, base_ref=base_ref,
                    head_ref=branch, attempts=attempts, repair_reports=repair_reports,
                    reasons=["safe_apply_bypassed"],
                )

            verification = list(hooks.verify(proposal, apply_outcome))
            after_rev = hooks.refresh_twin(proposal, apply_outcome) or ""

            patch_report = evaluate_patch_impact(
                policy=policy, brief=brief, base_ref=base_ref, head_ref=branch,
                git_result=git_result, changed_files=apply_outcome.changed_files,
                before_twin_revision_id=before_twin_revision_id,
                after_twin_revision_id=after_rev,
                verification=verification, twinproof=twinproof,
            )
            last_patch = patch_report
            last_ledger = create_proof_ledger_entry(
                requirement_ref=requirement_ref, plan_item_ref=plan_item_ref,
                policy=policy, brief=brief, patch_report=patch_report,
            )

            record = AttemptRecord(
                attempt=attempt, proposal_id=proposal.proposal_id,
                applied=apply_outcome.applied, decision=patch_report.decision.value,
                patch_report_id=patch_report.report_id,
                reasons=[*patch_report.blocked_reasons, *patch_report.repair_reasons],
            )

            if patch_report.decision == PatchGateDecision.ACCEPTED:
                attempts.append(record)
                return self._result(
                    PipelineStatus.ACCEPTED, policy=policy, brief=brief,
                    instruction_id=instruction.instruction_id, branch=branch, base_ref=base_ref,
                    head_ref=branch, attempts=attempts, patch_report=patch_report,
                    ledger_entry=last_ledger, repair_reports=repair_reports,
                    accepted=True, reasons=["patch_accepted"],
                )

            # Build targeted repair guidance for the next attempt (or final report).
            last_repair = build_repair_compass(
                policy=policy, brief=brief, patch_report=patch_report, ledger_entry=last_ledger,
            )
            repair_reports.append(last_repair)
            record.repair_report_id = last_repair.report_id
            attempts.append(record)

            # A hard boundary block cannot be repaired by looping.
            if patch_report.decision == PatchGateDecision.BLOCKED:
                return self._result(
                    PipelineStatus.BLOCKED, policy=policy, brief=brief,
                    instruction_id=instruction.instruction_id, branch=branch, base_ref=base_ref,
                    head_ref=branch, attempts=attempts, patch_report=patch_report,
                    ledger_entry=last_ledger, repair_reports=repair_reports,
                    reasons=["patch_blocked", *patch_report.blocked_reasons],
                )

        # 5) Loop exhausted without acceptance.
        return self._result(
            PipelineStatus.EXHAUSTED, policy=policy, brief=brief,
            instruction_id=instruction.instruction_id, branch=branch, base_ref=base_ref,
            head_ref=branch, attempts=attempts, patch_report=last_patch,
            ledger_entry=last_ledger, repair_reports=repair_reports,
            reasons=["repair_attempts_exhausted"],
        )


def _has_shadow_evidence(report: TwinShadowReport | None) -> bool:
    return report is not None and report.mode == TwinShadowMode.SHADOW


__all__ = [
    "ActiveIntegrationOrchestrator",
    "ActivePipelineResult",
    "ApplyOutcome",
    "AttemptRecord",
    "PipelineHooks",
    "PipelineMode",
    "PipelineStatus",
    "ProposalDraft",
]
