# Atlas Full Automation Codex Entrypoint

Use this file as the Codex starting point for the PR-E-0-G through PR-O practical full automation work.

## Read order

1. `AGENTS.md` when present.
2. `docs/atlas_pr_e_to_o_implementation_plan.md`.
3. `docs/atlas_pr_e0_b_hardening_instruction.md`.
4. `docs/atlas_corrective_pr_split_plan_after_1510.md`.
5. `docs/atlas_practical_full_automation_experience_plan.md`.
6. `docs/atlas_pr_e0_clarification_bugfix_plan.md`.
7. `docs/atlas_scale_master_roadmap.md`.
8. `docs/atlas_automation_phase_manifest.json`.
9. `docs/atlas_autonomous_execution_readiness_policy.md`.

## Required implementation order

The current implementation order is:

0. **PR-E-0-G** Align clarification UI blocking and automation truthfulness before PR-E.
1. **PR-E** Formalize clarification-driven plan revision loop.
2. **PR-F** Stabilize practical autonomous code-generation loop v1.
3. **PR-G** Integrate candidate workspace and recovery evidence.
4. **PR-H** Prepare evidence-backed draft PR artifacts.
5. **PR-I** Improve Atlas Workbench practical automation UX.
6. **PR-J** Add practical full automation end-to-end acceptance tests.
7. **PR-K** Add CI failure evidence and bounded repair planning.
8. **PR-L** Add self-platform candidate modification mode.
9. **PR-M** Add self-platform review gate before draft PR readiness.
10. **PR-N** Add supervised auto-merge readiness report.
11. **PR-O** Reconcile practical full automation completion and level semantics.

## Corrective plan after PR #1510

Before continuing broad full-automation expansion, Codex must follow:

- `docs/atlas_pr_e_to_o_implementation_plan.md`
- `docs/atlas_pr_e0_b_hardening_instruction.md`
- `docs/atlas_corrective_pr_split_plan_after_1510.md`

`docs/atlas_pr_e_to_o_implementation_plan.md` is the current follow-on implementation plan. It absorbs the earlier PR-E-0-B final audit into **PR-E-0-G** and then continues PR-E through PR-O one PR at a time.

`docs/atlas_pr_e0_b_hardening_instruction.md` remains the dedicated PR-E-0-B stabilization reference and PR-E-0-G must preserve its safety intent.

`docs/atlas_corrective_pr_split_plan_after_1510.md` remains the background corrective split plan for the #1510 over-declaration cleanup.

## Blocking note

PR-E-0-G is blocking before PR-E.

Do not proceed into PR-E or practical autonomous code-generation work while the following bugs remain:

- Clarification or post-clarification blockers can still show Approve/Run prompts.
- Independent clarification findings are not represented as independent clarification questions.
- Selecting one clarification answer clears remaining clarification questions.
- Same plan card or clarification card duplicates for the same pool/revision.
- `visual_contract_failed` lacks actionable missing details or is described as environment-only without evidence.
- Approval/execution is possible before clarification answers have caused plan revision and gate rerun evidence.
- Manifest/policy wording implies practical full automation is accepted complete before end-to-end evidence exists.
- Critical-event approval continuation lacks explicit bounded approved scope checks.

## Safety invariants

Always preserve:

- backend `workflow_state` / PlanPool authoritative
- UI display/supervision only
- no direct merge
- no remote git push
- no self-apply
- no stable runtime mutation
- no Vue authority or Vue default
- no arbitrary unbounded command execution
- no raw source serving, fallback redirect, or startup npm/Vite/Vue build
- no fabricated verification results
- critical events always require user judgment
- profile/envelope/gate boundaries

## Standalone corrective instructions

Some corrective work is tracked as dedicated single-goal Codex instructions that are
independent of the PR-E..PR-O order above:

- `docs/atlas_codex_workflow_state_truthfulness_instruction.md` — make the read-only
  `atlas.workflow_state.v1` contract truthful (profile/evidence-aware) so the supervision
  view stops reporting stale `level_0` / `SCALE-94 not callable` state while backend full
  automation is active. Display-only; adds no execution capability.

## Codex instruction

When running Codex in goal mode, instruct it to start from this file, then follow the read order and implementation order above. Keep PRs small, run focused tests first, run `py_compile` for changed Python files, and run `node --check` for changed JS files.