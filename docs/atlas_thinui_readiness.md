## Active PR Pointer (Updated)

Completed:
- PR-ATLAS-SCALE-76
- PR-ATLAS-SCALE-76B
- PR-ATLAS-SCALE-76C
- PR-ATLAS-SCALE-77
- PR-ATLAS-SCALE-77B
- PR-ATLAS-SCALE-78
- PR-ATLAS-SCALE-79
- PR-ATLAS-SCALE-80: out-of-order architecture checkpoint (docs/manifest/tests only; Vue migration plan + autonomous-first UI policy)
- PR-ATLAS-SCALE-81
- PR-ATLAS-SCALE-81B
- PR-ATLAS-SCALE-82

Current implementation PR:
- PR-ATLAS-SCALE-83: Risk classification gate foundation

Next implementation PR:
- PR-ATLAS-SCALE-84: Verification allowlist gate foundation

Known Current Code Facts:
- PR-82 completed patch transaction and rollback metadata foundation.
- Patch transactions are metadata-only and do not apply patches.
- Rollback metadata references manual snapshot restore.
- PR-78 added ThinUI contract tests and manifest-driven UI smoke.
- PR-79 defined autonomous execution readiness policy.
- PR-81 added workspace snapshot / restore foundation.
- PR-81B hardens snapshot / restore path safety.
- Snapshot source files must resolve under project_root.
- Symlinks are skipped by default and not followed.
- Symlink escapes are skipped / warned and not read.
- Restore source files must resolve under snapshot_dir.
- Restore destination files must resolve under project_path.
- delete_missing_before is plan-only / non-destructive for now.
- Snapshot artifacts are stored under resolved data_root.
- Path("ca_data") direct writes remain forbidden.
- Restore is manual-only.
- Automatic rollback remains disabled.
- Autonomous execution remains disabled.
- Atlas remains Level 0 manual-only execution at runtime.
- Autonomous execution remains forbidden until readiness gates pass.
- Required gates include snapshot/restore, patch transaction, risk classification, allowlisted verification, dry-run/approval, rollback readiness, artifact capture, stop/kill switch, loop bounds, remote git restrictions, and self-improvement gates.
- PR-79 does not enable auto-execution.
- PR-79 does not change runtime behavior.
- Primary CTA remains single existing manual action only.
- EXECUTE ONE ACTION remains required.
- Dry-run-first remains required.
- Suggested commands are not executed automatically.
- Backend workflow state remains authoritative.
- ThinUI remains replaceable and CLI-compatible.
- PR-80 remains an out-of-order architecture checkpoint and does not imply PR-79 was previously complete.
- Atlas final goal remains a fully autonomous code agent.
- Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope.

# Atlas ThinUI Readiness

## Purpose
- Current UI is too complex for normal operation.
- Existing UI exposes internal subsystems directly.
- Minimal workflow UI is required before full autonomous mode becomes usable.
- ThinUI does not change the final goal: a fully autonomous code agent.

## Final Goal Preserved
- Atlas final goal remains fully autonomous code agent.
- Goal path remains goal → research → plan → implement → test → fix → PR.
- Self-improving CodeAgentPersonal/KasaneCore remains in scope as a self-improving CodeAgentPersonal/KasaneCore platform objective.
- ThinUI is the frontend strategy for that goal.

## Current UI Problem
- Too many execution buttons are visible at once.
- Too many direct subsystem panels are visible by default.
- Raw IDs and JSON are visible by default.
- Normal users cannot tell which controls are required for normal flow.
- Detailed controls are useful for diagnostics, but should not be the default workflow. Advanced execution controls are hidden by default, not removed. Diagnostics remain accessible but should not be required for normal operation. UI hiding must not change execution semantics. Backend workflow state remains authoritative for browser, CLI, replacement UI, and future full-auto controller consumers of the same workflow contract.

## Minimal Workflow UI
Visible by default:
- task/goal input
- project path
- status/progress
- plan summary
- impact/verification summary
- approval handoff summary
- one primary CTA
- stop/reset
- copy/export approval context

## Advanced Execution Controls
Hidden by default:
- Build Queue
- Prepare
- Preview Token
- Advance to confirmation
- Execute confirmed action and refresh
- Next Action Orchestrator direct panel
- Multi-item Supervised Status
- Supervised Safe Apply
- Supervised Retry
- Patch Regen
- Candidate Approval direct panels

## Diagnostics / Developer Tools
Hidden by default:
- raw JSON panels
- repo index manual operations
- repo context manual operations
- PlanItem Impact Map direct button
- Context Refresh v2 direct button
- Planner Packaging v2 direct button
- Verification Recommendation direct button
- Verification Recommendation Handoff direct button
- direct pool_id/run_id/multi_status_run_id controls
- copy raw payload


## Automation-first UI / CLI Contract
- Atlas UI is not the source of workflow truth.
- Backend workflow state is authoritative.
- Browser ThinUI, future CLI, future replacement UI, and future full-auto controller must use the same high-level workflow contract.
- ThinUI supervision surface: task input, project path, status/progress, phase, approval summary, artifact summary, primary CTA, and stop/emergency control.
- UI must not encode execution decisions.
- Detailed panels are legacy/debug/advanced surfaces.
- Normal operation should not require direct low-level subsystem controls.
- ThinUI is replaceable and not the final goal replacement.
- Future CLI and replacement UI must not depend on current DOM structure.
- Final goal remains fully autonomous code agent and self-improving CodeAgentPersonal / KasaneCore platform.

## ThinUI Target Architecture
- UI should become a thin state display and approval surface.
- Backend remains responsible for workflow state.
- Frontend should not encode execution decisions.
- Future separate UI / CLI should be possible with the same backend APIs.

## Safety Requirements
- EXECUTE ONE ACTION remains required until policy explicitly changes.
- dry-run-first remains required.
- suggested commands are not executed automatically.
- advanced tools remain accessible.
- emergency stop/reset must remain visible.
- full-auto mode requires snapshot/restore/transaction/rollback readiness.

## PR-74〜80 UI Roadmap
- PR-74: Automation-first ThinUI / CLI workflow shell.
- PR-75: Hide advanced execution panels by default.
- PR-76: Diagnostics drawer and raw JSON isolation.
- PR-77: Atlas workflow state machine UI.
- PR-78: ThinUI contract tests and manifest-driven UI smoke.
- PR-79: Autonomous execution readiness policy checkpoint.
- PR-80: ThinUI architecture checkpoint.

## PR-81+ Autonomous Execution Roadmap
- See also: PR-91〜PR-100 Self-Improving Atlas / KasaneCore Roadmap
- workspace snapshot / restore foundation
- patch transaction manager
- autonomous execution policy v1
- auto verification loop
- auto patch regeneration loop
- full task autopilot v1
- self-improvement guardrails
- self-improving CodeAgentPersonal platform
- GitHub branch / draft PR automation
- autonomous development milestone


## Self-Improvement Scope
- Self-improvement remains explicitly in scope.
- Atlas must eventually be able to safely improve CodeAgentPersonal / KasaneCore itself.
- Self-improvement is not immediate full automation.
- Self-improvement requires stricter gates than ordinary repo work.
- Snapshot / restore / patch transaction / rollback readiness are required before autonomous self-modification.
- ThinUI is the supervision interface for autonomous and self-improving behavior.
- ThinUI does not replace self-improvement or autonomous execution.

- diagnostics remain accessible through toggles.
- replaceable UI target remains supported via the backend workflow contract.


## PR-80 Vue Migration Checkpoint
- Vue 3 + Vite + TypeScript selected for Atlas Next.
- Do not use Nuxt.
- No in-place `ui.html` rewrite.
- Backend-owned workflow state remains authoritative.
- Vue is parallel UI first.
- Classic UI becomes legacy only after parity tests pass.
- UI cleanup policy prevents future surface explosion.
- PR-80 is a docs/manifest/tests checkpoint only; no runtime UI replacement.

## Autonomous-first UI Cleanup
- Visible by default: goal/project path/plan summary/phase/status/current item/next action/primary CTA/approval/risk/verification/artifacts/progress timeline/stop-pause-emergency.
- Hidden by default: raw JSON/internal IDs/direct subsystem controls/manual internals/debug-only panels.
- Deprecate/remove rules: mark deprecated in manifest first; keep one migration PR when possible; never remove safety controls or diagnostics replacement paths.
- Every UI surface must be manifest-classified as minimal_workflow, safety_always_visible, advanced_execution, diagnostics, deprecated, or removed_after_migration.

## PR-76C Checkpoint Notes

- PR-76C fixes Diagnostics drawer structure after PR-76B.
- Diagnostics drawer is structurally bounded and does not wrap minimal workflow surfaces.
- Diagnostics section IDs exist and are manifest-covered.
- Raw JSON/result panels are diagnostics surfaces.
- Direct subsystem tools are diagnostics surfaces.
- Low-level ID fields are diagnostics surfaces where practical.
- PR-80 remains an out-of-order architecture checkpoint and does not imply PR-77〜79 are complete.
- Backend workflow state is authoritative.
- Execution semantics remain unchanged.
- EXECUTE ONE ACTION remains required for manual execution.
- Dry-run-first remains required.


## PR-77 Workflow State Machine UI Checkpoint
- Workflow primary CTA is derived from existing state (backend state remains authoritative).
- Primary CTA may trigger at most one existing manual action per click.
- No auto-continue and no execute-all.
- Dry-run-first remains required.
- EXECUTE ONE ACTION remains required.
- ThinUI remains replaceable and CLI-compatible.
- Final goal remains fully autonomous code agent and self-improving CodeAgentPersonal / KasaneCore.
- PR-80 remains out-of-order and does not imply PR-78〜79 are complete.
