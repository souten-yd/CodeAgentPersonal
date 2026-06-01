# Atlas Full Automation Codex Entrypoint

Use this file as the Codex starting point for the A-J practical full automation work.

## Read order

1. `AGENTS.md` when present.
2. `docs/atlas_practical_full_automation_experience_plan.md`.
3. `docs/atlas_pr_e0_clarification_bugfix_plan.md`.
4. `docs/atlas_corrective_pr_split_plan_after_1510.md`.
5. `docs/atlas_scale_master_roadmap.md`.
6. `docs/atlas_automation_phase_manifest.json`.
7. `docs/atlas_autonomous_execution_readiness_policy.md`.

## Required implementation order

The current implementation order is:

1. **PR-A** Critical-event NG replanning connection.
2. **PR-B** Pool-level critical-event approval visibility.
3. **PR-C** Profile/preset/envelope schema unification.
4. **PR-D** Docs/manifest/policy alignment.
5. **PR-E-0 / PR-E-Bugfix** Clarification UX/state bugs and visual verification surfacing.
6. **PR-E** Clarification-driven plan revision loop.
7. **PR-F** Practical autonomous code-generation loop v1.
8. **PR-G** Candidate workspace and recovery integration.
9. **PR-H** Draft PR preparation and update experience.
10. **PR-I** UI and API practical automation experience.
11. **PR-J** End-to-end acceptance tests.

## Corrective plan after PR #1510

Before continuing broad A-J/full-automation expansion, Codex must follow:

- `docs/atlas_corrective_pr_split_plan_after_1510.md`

That corrective plan folds the latest user feedback and review findings into four small PR tracks:

1. PR-1 / P0: clarification execution safety blocker.
2. PR-2 / P1: clarification UX and concrete remediation options.
3. PR-3 / P1: repairable verification failure bounded repair loop.
4. PR-4 / P0/P1: manifest truthfulness, orchestrator preflight hardening, critical-event continuation scope, and acceptance/safety contract tests.

## Blocking note

PR-E-0 is blocking before PR-E and PR-F.

Do not proceed into the clarification-driven plan revision loop or practical autonomous code-generation loop while the following bugs remain:

- Independent clarification findings rendered as one shared option list.
- Selecting one clarification answer clears all remaining clarification questions.
- Same plan card duplicated for the same pool/revision.
- `visual_contract_failed` shown without actionable missing contract details.
- Approval/execution possible before clarification answers have caused plan revision and gate rerun.
- A-J/full automation is over-declared as complete before end-to-end, safety, and acceptance contracts are actually verified.
- Critical-event approval continuation lacks explicit bounded approved scope checks.

## Safety invariants

Always preserve:

- backend `workflow_state` authoritative
- UI display/supervision only
- no direct merge
- no remote git push
- no self-apply
- no stable runtime mutation
- no Vue authority
- no arbitrary unbounded command execution
- no fabricated verification results
- critical events always require user judgment

## Codex instruction

When running Codex in goal mode, instruct it to start from this file, then follow the read order and implementation order above. Keep PRs small, run focused tests first, run `py_compile` for changed Python files, and run `node --check` for changed JS files.