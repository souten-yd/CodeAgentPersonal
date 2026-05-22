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
- PR-ATLAS-SCALE-83
- PR-ATLAS-SCALE-84
- PR-ATLAS-SCALE-84B
- PR-ATLAS-SCALE-85
- PR-ATLAS-SCALE-86
- PR-ATLAS-SCALE-87
- PR-ATLAS-SCALE-88
- PR-ATLAS-SCALE-89
- PR-ATLAS-SCALE-90
- PR-ATLAS-SCALE-90B
- PR-ATLAS-SCALE-91

Current implementation PR:
- PR-ATLAS-SCALE-92: Readiness gate rollup / Level-0 completion checkpoint

Next implementation PR:
- PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint

Known Current Code Facts:
- PR-90B hardens remote git reference-readiness blocking.
- requested_operation must be "none" for remote git readiness.
- requested_operation="unknown" blocks remote git readiness.
- Invalid or unreadable reference manifests block remote git readiness.
- remote_git_gate_ready does not authorize git operations.
- PR-91 adds self-improvement gate consolidation.
- Self-improvement gate is metadata-only and does not modify code.
- Self-improvement gate does not generate patches.
- Self-improvement gate does not apply patches.
- Self-improvement gate does not run safe_apply.
- Self-improvement gate does not run tests or verification.
- Self-improvement gate does not run git commands.
- self_improvement_gate_ready does not authorize automatic execution.
- self_improvement_gate_ready does not authorize patch apply.
- self_improvement_gate_ready does not authorize git operations.
- Autonomous self-improvement remains disabled.
- Automatic self-modification remains disabled.
- Self-modification is strict-gate by default.
- Runtime, execution semantics, safety policy, autonomous controls, remote git policy, data_root, and UI workflow state are strict-gate by default.
- Self-improvement readiness requires snapshot, patch transaction, risk classification, verification allowlist, dry-run approval, rollback readiness, artifact capture, stop gate, loop bound, and remote git gate evidence.
- PR-90 adds remote git gate consolidation.
- Remote git gate is metadata-only and does not run git commands.
- Remote git gate does not push, pull, clone, fetch, or mutate remotes.
- Remote git gate does not create branches.
- Remote git gate does not create PRs.
- Remote git gate does not merge PRs.
- Direct merge remains forbidden.
- Automatic PR creation remains disabled.
- Draft PR creation requires a future explicit policy PR.
- Remote git operation requests are blocked as policy metadata.
- remote_git_gate_ready does not authorize git operations.
- PR-89 added loop bound gate consolidation.
- Loop bound gate is metadata-only and does not run loops.
- Loop bound gate does not retry automatically.
- Loop bound gate does not continue automatically.
- Loop bound gate does not authorize automatic execution.
- Explicit bounds are required for max actions, retries, runtime, files changed, risk level, consecutive failures, verification attempts, and patch transactions.
- No unbounded autonomous loop is allowed.
- Auto-continue remains disabled.
- Execute-all remains forbidden.
- Automatic loop execution remains disabled.
- Automatic retry remains disabled.
- PR-88 adds stop / kill switch gate consolidation.
- Stop / kill switch gate is metadata-only and does not stop real jobs.
- Stop / kill switch gate does not kill processes.
- Stop acknowledgement is not fabricated.
- Stop state is recorded for future UI/CLI inspection.
- Stop gate blocks readiness if auto-continue or execute-all is enabled.
- Stop gate blocks readiness if required stop controls are missing.
- No auto-continue after stop remains required.
- Execute-all remains forbidden.
- Automatic stop execution remains disabled.
- Artifact capture gate is metadata-only and does not execute actions.
- Artifact capture does not create fake execution results.
- Artifact capture does not create fake verification results.
- Artifact capture records references and missing evidence explicitly.
- Artifact capture records are stored under resolved data_root.
- Plan, snapshot, patch transaction, rollback metadata, risk classification, verification allowlist, dry-run approval gate, and rollback readiness gate references are required for readiness.
- Dry-run result, execution result, verification plan, and verification result references are tracked when available; missing results are recorded explicitly.
- Warnings and recovery instructions are captured.
- Artifacts remain inspectable from future UI/CLI.
- Automatic artifact capture remains disabled.
- PR-84 added verification allowlist gate foundation.
- PR-84B fixed verification allowlist py_compile / node check contracts.
- PR-85 added dry-run and approval gate consolidation.
- PR-86 adds rollback readiness gate consolidation.
- Rollback readiness gate is metadata-only and does not restore files.
- Rollback readiness does not execute rollback automatically.
- Rollback readiness does not authorize automatic execution.
- Snapshot manifest and rollback metadata are required for readiness.
- Restore plan is required for readiness.
- Rollback strategy remains manual snapshot restore.
- Restore remains manual-only.
- Automatic restore remains disabled.
- Automatic rollback remains disabled.
- Autonomous execution remains disabled.
- Dry-run / approval gate is metadata-only and does not execute actions.
- Gate readiness does not authorize automatic execution.
- Gate readiness does not execute automatically.
- Dry-run-first remains mandatory.
- EXECUTE ONE ACTION remains required.
- Confirmation token or future equivalent approval token remains mandatory.
- Explicit approval is mandatory for medium/high/strict risk.
- strict_gate always requires explicit approval.
- Missing or failed dry-run blocks readiness.
- Automatic dry-run remains disabled.
- Automatic approval remains disabled.
- Automatic execute remains disabled.
- Verification allowlist is metadata-only and does not execute commands.
- Allowlisted command means eligible for future guarded/manual verification, not automatic execution.
- Broad shell, remote git, destructive commands, package installs, shell metacharacters, and arbitrary commands are blocked.
- Recommended commands remain suggestions only.
- Automatic command execution remains disabled.
- PR-83 adds risk classification gate foundation.
- Risk classification is metadata-only and does not authorize execution.
- Unknown risk is not low risk.
- Runtime, launcher, Docker, execution APIs, data_root, safety docs, UI workflow state, and self-modification are strict-gate by default.
- Automatic safe_apply remains disabled.
- Automatic verification remains disabled.
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


## PR-ATLAS-SCALE-84B Checkpoint Update

Completed PR: PR-ATLAS-SCALE-84B (Fix verification allowlist py_compile / node check contracts).

Current implementation PR:
- PR-ATLAS-SCALE-85: Dry-run and approval gate consolidation

Next implementation PR:
- PR-ATLAS-SCALE-86: Rollback readiness gate consolidation

Known Current Code Facts:
- PR-90B hardens remote git reference-readiness blocking.
- requested_operation must be "none" for remote git readiness.
- requested_operation="unknown" blocks remote git readiness.
- Invalid or unreadable reference manifests block remote git readiness.
- remote_git_gate_ready does not authorize git operations.
- PR-91 adds self-improvement gate consolidation.
- Self-improvement gate is metadata-only and does not modify code.
- Self-improvement gate does not generate patches.
- Self-improvement gate does not apply patches.
- Self-improvement gate does not run safe_apply.
- Self-improvement gate does not run tests or verification.
- Self-improvement gate does not run git commands.
- self_improvement_gate_ready does not authorize automatic execution.
- self_improvement_gate_ready does not authorize patch apply.
- self_improvement_gate_ready does not authorize git operations.
- Autonomous self-improvement remains disabled.
- Automatic self-modification remains disabled.
- Self-modification is strict-gate by default.
- Runtime, execution semantics, safety policy, autonomous controls, remote git policy, data_root, and UI workflow state are strict-gate by default.
- Self-improvement readiness requires snapshot, patch transaction, risk classification, verification allowlist, dry-run approval, rollback readiness, artifact capture, stop gate, loop bound, and remote git gate evidence.
- PR-90 adds remote git gate consolidation.
- Remote git gate is metadata-only and does not run git commands.
- Remote git gate does not push, pull, clone, fetch, or mutate remotes.
- Remote git gate does not create branches.
- Remote git gate does not create PRs.
- Remote git gate does not merge PRs.
- Direct merge remains forbidden.
- Automatic PR creation remains disabled.
- Draft PR creation requires a future explicit policy PR.
- Remote git operation requests are blocked as policy metadata.
- remote_git_gate_ready does not authorize git operations.
- PR-89 added loop bound gate consolidation.
- Loop bound gate is metadata-only and does not run loops.
- Loop bound gate does not retry automatically.
- Loop bound gate does not continue automatically.
- Loop bound gate does not authorize automatic execution.
- Explicit bounds are required for max actions, retries, runtime, files changed, risk level, consecutive failures, verification attempts, and patch transactions.
- No unbounded autonomous loop is allowed.
- Auto-continue remains disabled.
- Execute-all remains forbidden.
- Automatic loop execution remains disabled.
- Automatic retry remains disabled.
- PR-88 adds stop / kill switch gate consolidation.
- Stop / kill switch gate is metadata-only and does not stop real jobs.
- Stop / kill switch gate does not kill processes.
- Stop acknowledgement is not fabricated.
- Stop state is recorded for future UI/CLI inspection.
- Stop gate blocks readiness if auto-continue or execute-all is enabled.
- Stop gate blocks readiness if required stop controls are missing.
- No auto-continue after stop remains required.
- Execute-all remains forbidden.
- Automatic stop execution remains disabled.
- Artifact capture gate is metadata-only and does not execute actions.
- Artifact capture does not create fake execution results.
- Artifact capture does not create fake verification results.
- Artifact capture records references and missing evidence explicitly.
- Artifact capture records are stored under resolved data_root.
- Plan, snapshot, patch transaction, rollback metadata, risk classification, verification allowlist, dry-run approval gate, and rollback readiness gate references are required for readiness.
- Dry-run result, execution result, verification plan, and verification result references are tracked when available; missing results are recorded explicitly.
- Warnings and recovery instructions are captured.
- Artifacts remain inspectable from future UI/CLI.
- Automatic artifact capture remains disabled.
- PR-84B fixes verification allowlist py_compile / node check contracts.
- Verification allowlist is metadata-only and does not execute commands.
- python -m py_compile <safe relative file> is allowlisted metadata only.
- node --check web/js/<safe js file> is allowlisted metadata only.
- Targeted pytest -q tests/<safe test file>.py is allowlisted metadata only.
- Allowlisted means future guarded/manual verification eligibility, not execution authorization.
- Automatic verification remains disabled.
- Automatic command execution remains disabled.
- Automatic safe_apply remains disabled.
- Automatic patch generation remains disabled.
- Automatic patch apply remains disabled.
- Automatic rollback remains disabled.
- Autonomous execution remains disabled.
- Level 0 manual-only remains.
- EXECUTE ONE ACTION remains required.
- Dry-run-first remains required.
- PR-80 remains an out-of-order architecture checkpoint.
- Atlas final goal remains a fully autonomous code agent.
- Self-improving CodeAgentPersonal / KasaneCore remains in scope.


## PR-ATLAS-SCALE-91B Checkpoint Update

Completed PR: PR-ATLAS-SCALE-91B.
Current implementation PR: PR-ATLAS-SCALE-92: Readiness gate rollup / Level-0 completion checkpoint.
Next implementation PR: PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint.
PR-91B fixes self-improvement gate integration wiring and evaluated-payload persistence.
PR-91C fixes the final self-improvement manifest contract drift.
self_improvement_scope is self_improving_codeagentpersonal_kasanecore.
final_goal remains fully_autonomous_code_agent.
Invalid or unreadable referenced manifests block self-improvement readiness.
Self-improvement gate is metadata-only and does not modify code, generate patches, apply patches, run safe_apply, run tests or verification, or run git commands.
Autonomous self-improvement remains disabled; automatic self-modification remains disabled; self-modification is strict-gate by default.
self_improvement_gate_ready does not authorize automatic execution, patch apply, or git operations.
Automatic command execution, patch generation, patch apply, safe_apply, verification, restore, rollback, loop execution, and retry remain disabled.
auto-continue remains disabled; execute-all remains forbidden; autonomous execution remains disabled.
Atlas runtime remains Level 0 manual-only and primary CTA remains single existing manual action only.


- Vue implementation has not started in this PR series.


## PR-ATLAS-SCALE-92 Level-0 Completion Checkpoint
- PR-ATLAS-SCALE-92 completed the Level-0 metadata-only readiness foundation via readiness gate rollup.
- Level-0 completion checkpoint is metadata-only and does not enable Level-1 execution.
- Level-0 completion does not authorize autonomous execution, patch generation/apply, safe_apply, verification execution, rollback/restore, or git operations.
- Runtime remains Level 0 manual-only.
- Current implementation PR is PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint.
- Vue implementation is allowed only after PR-92 is merged and has not started in PR-92.
- Separate UI track after merge: PR-ATLAS-VUE-01 read-only parallel UI track; existing ui.html remains default and backend workflow_state remains authoritative.
- PR-80 remains Vue migration planning checkpoint and did not add Vue runtime code.
- automatic command execution disabled; automatic verification disabled; automatic patch generation disabled; automatic patch apply disabled; automatic safe_apply disabled; automatic rollback disabled; automatic restore disabled; automatic loop execution disabled; automatic retry disabled; auto-continue disabled; execute-all forbidden; autonomous execution disabled; autonomous self-improvement disabled; remote git disabled; direct merge forbidden; primary CTA remains single existing manual action only.

- Existing ui.html remains the default UI.

## PR-ATLAS-VUE-04 checkpoint
- Completed: safe GET adapter/static mount decision.
- GET adapter deferred (`deferred_no_stable_get_contract`) until stable backend read-only workflow_state contract exists.
- Static mount deferred (`deferred_no_dist_strategy`) until dist artifact strategy is locked.
- Vue remains read-only/parallel/not default; `ui.html` remains default.
- Backend workflow state remains authoritative; available actions in Vue remain metadata-only.


## PR-ATLAS-VUE-06 Contract Binding Checkpoint
- PR-ATLAS-VUE-06 completed: Vue read-only adapter is bound to `GET /api/atlas/workflow-state/read-only`.
- Adapter remains GET-only and fallback-safe: invalid/non-OK responses use a placeholder read-only snapshot fallback.
- `available_actions` remain metadata only; all actions are disabled/read-only in Vue.
- Backend workflow state remains authoritative; Vue does not compute execution eligibility and does not call mutation endpoints.
- Vue remains parallel/read-only/not default; existing `ui.html` remains default.
- Static mount remains deferred while dist/static artifact strategy is not locked.
- Automation track remains `PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint`.
- Final goal remains `fully_autonomous_code_agent` and self-improvement scope remains `self_improving_codeagentpersonal_kasanecore`.

## PR-ATLAS-VUE-07 Read-only Parity + Visual Refinement
- Completed UI PR: PR-ATLAS-VUE-07.
- Vue read-only parity tests were added and visual refinement is documented.
- Vue remains read-only/not default/no execution and existing ui.html remains default.
- Backend workflow state remains authoritative.
- available_actions remain metadata only and disabled/read-only in Vue.
- Vue does not compute execution eligibility and does not call mutation endpoints.
- Vue adapter remains GET-only at /api/atlas/workflow-state/read-only with fallback.
- Static mount remains deferred until safe dist/static strategy is locked.
- Automation track remains PR-ATLAS-SCALE-93.
- Current UI track after this PR: PR-ATLAS-VUE-08.
