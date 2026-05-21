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

Current implementation PR:
- PR-ATLAS-SCALE-91: Self-improvement gate consolidation

Next implementation PR:
- PR-ATLAS-SCALE-92: Readiness gate rollup / Level-0 completion checkpoint

Known Current Code Facts:
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
- Atlas remains Level 0 manual-only at runtime.
- Automatic patch apply remains disabled.
- Automatic patch generation remains disabled.
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

# Atlas Development Handoff

## Current Status
- Completed baseline: PR-ATLAS-PIPE-0〜60D, PR-ATLAS-SCALE-61〜72.
- PR-ATLAS-SCALE-74 adds automation-first ThinUI / CLI workflow shell contract and minimal workflow shell surfaces.
- Runtime behavior is unchanged in this PR.

## Safety Boundaries (Unchanged)
- no execute all / no auto continue
- no shell=True / no remote git
- no automatic safe_apply / verification / retry / patch generation / test execution
- human confirmation required for execution

## Historical Notes (Clearly Historical)
- Historical roadmap/doc updates: PR-ATLAS-DOCS-ROADMAP-01, PR-ATLAS-DOCS-ROADMAP-02, PR-ATLAS-DOCS-CONSTITUTION-01, PR-ATLAS-DOCS-QUALITY-GATE-01.
- Historical implementation marker: PR-ATLAS-SCALE-70 (completed).
- Historical implementation marker: PR-ATLAS-SCALE-72 (completed).

## Development Restart Instructions
Before making changes:
1. Read docs/atlas_development_handoff.md
2. Read docs/atlas_scale_master_roadmap.md
3. Read docs/atlas_unified_autopilot_checkpoint.md
4. Confirm the latest merged PR on GitHub
5. Inspect main branch files directly before trusting PR body text
6. Verify actual files, tests, and runtime wiring

Hard safety rules:
- preserve classic script contract
- preserve confirmation token / `EXECUTE ONE ACTION`
- preserve dry-run-first behavior
- keep ThinUI as an interface goal, not a product-goal replacement
- update checkpoint docs after every PR

## Required Final PR Report Format
- Completed PR
- Current PR
- Next PR
- Files changed
- Tests run
- Grep/safety checks
- Known limitations
- Safety confirmation
- Whether follow-up PR is required

## Constitution / Checklist References
- docs/atlas_development_constitution.md
- docs/atlas_preflight_checklist.md
- docs/atlas_postflight_checklist.md
- docs/atlas_pr_template.md
- docs/atlas_self_development_rules.md
- Historical quality marker: PR-ATLAS-SCALE-65B.

- Diagnostics remain accessible through toggles and are hidden by default, not removed.

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


## Historical Pointer (Legacy Contracts)
Current PR:
- PR-ATLAS-SCALE-76
Next PR:
- PR-ATLAS-SCALE-77: Atlas workflow state machine UI
Completed:
- PR-ATLAS-SCALE-75
- PR-ATLAS-SCALE-76


- PR-77 adds workflow state machine UI for the automation-first shell.
- Workflow primary CTA is derived from existing state.
- Primary CTA may trigger at most one existing manual action per click.
- Primary CTA does not auto-continue.
- Primary CTA does not execute all.
- Primary CTA does not bypass dry-run-first.
- Primary CTA does not bypass EXECUTE ONE ACTION.
- Backend workflow state remains authoritative.
- ThinUI remains replaceable and CLI-compatible.
- PR-80 remains an out-of-order architecture checkpoint and does not imply PR-79 is complete.
- Atlas final goal remains a fully autonomous code agent.
- Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope.
- Execution semantics remain unchanged.


## PR-ATLAS-SCALE-84B Checkpoint Update

Completed PR: PR-ATLAS-SCALE-84B (Fix verification allowlist py_compile / node check contracts).

Current implementation PR:
- PR-ATLAS-SCALE-85: Dry-run and approval gate consolidation

Next implementation PR:
- PR-ATLAS-SCALE-86: Rollback readiness gate consolidation

Known Current Code Facts:
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
