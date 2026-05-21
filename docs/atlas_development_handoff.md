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
