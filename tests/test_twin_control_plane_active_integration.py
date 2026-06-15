"""TFG-11 / Package 11 — Active integration behind a gate tests.

Proves the gated, reversible active pipeline:

- OFF (and ``disabled``) returns a no-op and applies nothing;
- ACTIVE without shadow evidence is BLOCKED and generates nothing;
- ACTIVE with shadow evidence runs the full loop and accepts a clean patch with a
  Proof Ledger entry;
- a Safe Apply bypass (applied without ``via_safe_apply``) is BLOCKED;
- a failing gate drives a Repair Compass loop and can recover or exhaust;
- SHADOW mode is a dry run that never applies;
- local Git branch prep blocks on a dirty worktree (real temp repo) and never touches
  the remote.
"""
from __future__ import annotations

import subprocess

from agent.git_steward.local_adapter import (
    create_baseline_commit,
    harden_ignore_policy,
    initialize_repository,
)
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.active_integration import (
    ActiveIntegrationOrchestrator,
    ApplyOutcome,
    PipelineHooks,
    PipelineMode,
    PipelineStatus,
    ProposalDraft,
)
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
    default_hard_constraints,
)
from agent.twin_control_plane.patch_impact_gate import VerificationEvidence
from agent.twin_control_plane.shadow_integration import TwinShadowMode, TwinShadowReport


def _policy(required_gates=None) -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policyA", route=ForgeRoute.DIRECT_PATCH, model_id="local-coder",
        instruction_style=InstructionStyle.CONSTRAINED_PATCH,
        model_capability_mode=ModelCapabilityMode.WEAK_LOCAL,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        required_gates=required_gates or ["SafeApplyBoundary", "RemotePublishApprovalGate"],
        hard_constraints=default_hard_constraints(),
    )


def _brief() -> TwinBrief:
    return TwinBrief(
        brief_id="briefA", goal="add feature safely", allowed_refs=["py://feature.entry"],
        hard_constraints=[TwinConstraint(constraint_id="c1", text="Preserve API.")],
        required_tests=["test://feature"], proof_requirements=["prove feature"],
    )


def _shadow_report() -> TwinShadowReport:
    return TwinShadowReport(report_id="twin_shadow:plan1", mode=TwinShadowMode.SHADOW,
                            plan_item_ref="plan1")


def _proposal() -> ProposalDraft:
    return ProposalDraft(proposal_id="prop1", summary="add feature",
                         changed_files=["py/feature.py"])


def _passing_hooks() -> PipelineHooks:
    return PipelineHooks(
        generate=lambda instr, repair: _proposal(),
        safe_apply=lambda proposal: ApplyOutcome(applied=True, via_safe_apply=True,
                                                 changed_files=proposal.changed_files,
                                                 commit_sha="sha1"),
        verify=lambda proposal, apply: [VerificationEvidence(
            evidence_id="ev_feature", status="passed", command="pytest -q test_feature.py")],
        refresh_twin=lambda proposal, apply: "tw_after",
    )


def test_off_mode_is_noop():
    orch = ActiveIntegrationOrchestrator(PipelineMode.OFF)
    result = orch.run(policy=_policy(), brief=_brief(), hooks=_passing_hooks())
    assert result.status == PipelineStatus.OFF
    assert result.accepted is False
    assert result.attempts == []


def test_disabled_behaves_as_off():
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, disabled=True)
    assert orch.mode == PipelineMode.OFF
    result = orch.run(policy=_policy(), brief=_brief(), hooks=_passing_hooks(),
                      shadow_report=_shadow_report(), before_twin_revision_id="tw_before")
    assert result.status == PipelineStatus.OFF


def test_active_requires_shadow_evidence():
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE)
    result = orch.run(policy=_policy(), brief=_brief(), hooks=_passing_hooks(),
                      before_twin_revision_id="tw_before")  # no shadow_report
    assert result.status == PipelineStatus.BLOCKED
    assert result.requires_shadow_evidence is True
    assert "active_requires_shadow_evidence" in result.reasons
    assert result.attempts == []  # nothing generated


def test_active_accepts_clean_patch_with_ledger():
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE)
    result = orch.run(
        policy=_policy(), brief=_brief(), hooks=_passing_hooks(),
        requirement_ref="req1", plan_item_ref="plan1",
        shadow_report=_shadow_report(), before_twin_revision_id="tw_before",
    )
    assert result.status == PipelineStatus.ACCEPTED
    assert result.accepted is True
    assert result.patch_report.accepted is True
    assert result.ledger_entry is not None and result.ledger_entry.accepted is True
    assert len(result.attempts) == 1


def test_safe_apply_bypass_is_blocked():
    hooks = PipelineHooks(
        generate=lambda instr, repair: _proposal(),
        # Applied WITHOUT going through Safe Apply -> hard boundary violation.
        safe_apply=lambda proposal: ApplyOutcome(applied=True, via_safe_apply=False,
                                                 changed_files=["py/feature.py"]),
    )
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE)
    result = orch.run(policy=_policy(), brief=_brief(), hooks=hooks,
                      shadow_report=_shadow_report(), before_twin_revision_id="tw_before")
    assert result.status == PipelineStatus.BLOCKED
    assert "safe_apply_bypassed" in result.reasons
    assert result.accepted is False


def test_failed_verification_drives_repair_then_exhausts():
    hooks = PipelineHooks(
        generate=lambda instr, repair: _proposal(),
        safe_apply=lambda proposal: ApplyOutcome(applied=True, via_safe_apply=True,
                                                 changed_files=["py/feature.py"]),
        # Verification keeps failing -> needs_repair every attempt.
        verify=lambda proposal, apply: [VerificationEvidence(
            evidence_id="ev_feature", status="failed", command="pytest")],
        refresh_twin=lambda proposal, apply: "tw_after",
    )
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, max_repair_attempts=2)
    result = orch.run(policy=_policy(), brief=_brief(), hooks=hooks,
                      shadow_report=_shadow_report(), before_twin_revision_id="tw_before")
    assert result.status == PipelineStatus.EXHAUSTED
    assert len(result.attempts) == 2
    assert result.repair_reports  # Repair Compass guidance produced
    assert result.accepted is False


def test_repair_loop_recovers_on_second_attempt():
    calls = {"n": 0}

    def verify(proposal, apply):
        calls["n"] += 1
        status = "failed" if calls["n"] == 1 else "passed"
        return [VerificationEvidence(evidence_id="ev_feature", status=status, command="pytest")]

    hooks = PipelineHooks(
        generate=lambda instr, repair: _proposal(),
        safe_apply=lambda proposal: ApplyOutcome(applied=True, via_safe_apply=True,
                                                 changed_files=["py/feature.py"]),
        verify=verify,
        refresh_twin=lambda proposal, apply: "tw_after",
    )
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, max_repair_attempts=3)
    result = orch.run(policy=_policy(), brief=_brief(), hooks=hooks,
                      shadow_report=_shadow_report(), before_twin_revision_id="tw_before")
    assert result.status == PipelineStatus.ACCEPTED
    assert len(result.attempts) == 2
    assert result.repair_reports  # the first failing attempt produced repair guidance


def test_shadow_mode_is_dry_run_and_never_applies():
    applied = {"count": 0}

    def safe_apply(proposal):
        applied["count"] += 1
        return ApplyOutcome(applied=True, via_safe_apply=True)

    hooks = PipelineHooks(generate=lambda instr, repair: _proposal(), safe_apply=safe_apply)
    orch = ActiveIntegrationOrchestrator(PipelineMode.SHADOW)
    result = orch.run(policy=_policy(), brief=_brief(), hooks=hooks)
    assert result.status == PipelineStatus.SHADOW
    assert applied["count"] == 0  # Safe Apply hook never invoked in shadow
    assert result.accepted is False


def _init_repo(path):
    initialize_repository(path)
    harden_ignore_policy(path)
    # An initial committed file so HEAD exists.
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    create_baseline_commit(path)
    return path


def test_branch_prep_blocks_on_dirty_worktree(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    # Make the worktree dirty.
    (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE)
    result = orch.run(
        policy=_policy(), brief=_brief(), hooks=_passing_hooks(),
        plan_item_ref="plan1", repo_path=str(repo), shadow_report=_shadow_report(),
        before_twin_revision_id="tw_before",
    )
    assert result.status == PipelineStatus.BLOCKED
    assert "git_branch_prep_blocked" in result.reasons
    # The remote was never touched: only a local branch op was attempted.
    branches = subprocess.run(["git", "branch"], cwd=str(repo), text=True,
                              capture_output=True).stdout
    assert "atlas/plan1" not in branches  # blocked before checkout


def test_branch_prep_succeeds_on_clean_repo_and_accepts(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE)
    result = orch.run(
        policy=_policy(), brief=_brief(), hooks=_passing_hooks(),
        plan_item_ref="plan1", repo_path=str(repo), shadow_report=_shadow_report(),
        before_twin_revision_id="tw_before",
    )
    assert result.status == PipelineStatus.ACCEPTED
    assert result.branch == "atlas/plan1"
    branches = subprocess.run(["git", "branch"], cwd=str(repo), text=True,
                              capture_output=True).stdout
    assert "atlas/plan1" in branches
