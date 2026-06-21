# KasaneCore Agent Instructions

## Active Goal

The current active track is **Forge / Twin / Arena / Anvil 統合改修** (Method layer: MethodVariant / MethodAdapter / MethodRouter / MethodPipeline + Arena radar + weak-LLM reinforcement).

**START HERE — read this one file first, it is self-sufficient to begin:**

```text
docs/forge_twin_arena_anvil_integration_agent_entrypoint.md
```

It contains: the read order, the per-item PR workflow, the verified test command, the hard invariants, the `decomposition_policy.py` naming-collision warning, the existing foundation to reuse, the full 16-PR list, and an unambiguous PR1 spec to start from. Supporting docs:

1. `docs/forge_twin_arena_anvil_integration_plan.md` — living plan + 16-PR breakdown + progress tracker (update before/after each item)
2. `docs/forge_twin_arena_anvil_integration_current_status.md` — Phase 0 inventory / component classification

Work item = 1 PR. The user has explicitly authorized creating and merging a PR per item for this track (2026-06-21; the plan itself merged as PR #1960). Branch per item (`feat/forge-method-*`), implement + test, then PR + merge. Do not replace existing modules — integrate/extend. **Next to start: PR1 (feat/forge-method-contracts).** Test command: `venv_sys/Scripts/python.exe -m pytest -q tests/<file>.py`.

The prior default development goal is **Atlas Twin / Forge / Git Steward**.

Start here for all general implementation work unless the user explicitly asks for another track:

1. `docs/atlas_twin_forge_git_steward_goal_mode_execution.md`
2. `docs/atlas_twin_forge_git_steward_current_status.md`
3. `docs/atlas_twin_forge_git_steward_agent_entrypoint.md`
4. `docs/atlas_twin_forge_git_steward_detailed_plan.md` only when more detail is needed

Begin with Package 0 from the goal-mode document:

```bash
python -m pytest -q tests/test_twin_forge_git_steward_initial.py
```

If focused tests fail due to type, import, pydantic, enum, or module-path mismatches, repair those first, record exact evidence in the current status doc, then continue the package sequence.

## Completed / Reference Tracks

AUIR, PIBIH, PIR, PFG, Portal, Play, Capsule, Forge foundation, and prior Portal/Forge hardening are completed or reference tracks. Do not start from them by default.

Use them only when touching their area or when the user explicitly asks.

Reference docs include:

```text
docs/atlas_runtime_progress_resume_hardening_current_status.md
docs/atlas_runtime_progress_resume_hardening_plan.md
docs/atlas_runtime_progress_resume_hardening_test_plan.md
docs/atlas_runtime_progress_resume_hardening_agent_entrypoint.md

docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
docs/atlas_project_intelligence_behavioral_impact_hardening_plan.md
docs/atlas_project_intelligence_behavioral_impact_hardening_test_plan.md
docs/atlas_project_intelligence_behavioral_impact_hardening_agent_entrypoint.md

docs/atlas_project_intelligence_recovery_current_status.md
docs/atlas_project_intelligence_recovery_master_goal.md
docs/atlas_portal_forge_current_status.md
docs/atlas_portal_forge_master_goal.md
docs/atlas_portal_forge_detailed_design.md
docs/atlas_portal_forge_implementation_plan.md
docs/atlas_portal_forge_test_plan.md
docs/atlas_portal_forge_hardening_current_status.md
docs/atlas_portal_forge_hardening_plan.md
docs/atlas_portal_forge_hardening_test_plan.md
docs/atlas_portal_forge_hardening_agent_entrypoint.md
```

## Must Preserve

* `unavailable` is not `passed`.
* Mock results are not live evidence.
* UI rendering is not runtime evidence.
* Inferred graph facts are not verified facts.
* Project Intelligence is advisory context and evidence, not execution authority.
* Atlas owns requirement, PlanPool, Proposal, Safe Apply, Verification, Repair, and Convergence.
* Portal owns runtime execution, artifact lifecycle, generated-data save/discard, and Capsule replay.
* Forge owns model/provider/profile routing and benchmark evidence.
* Nexus owns external web research. External/web calls remain policy-gated and disabled by default.
* No code path may bypass Proposal / Safe Apply / Verification.
* No external provider may run in Local Only mode.
* Secrets must never be persisted, logged, returned by API, embedded in Capsule ZIPs, or included in Project Intelligence stores.
* Capsule package ZIPs must remain immutable and data-free by default.
* Implementation size alone is not a stop condition.

## Local Git Policy

Local Git operations are allowed inside the local repository and Atlas-owned work area:

* status/diff/log inspection;
* local branch/worktree creation;
* local commits/checkpoints;
* fetch/pull/clone from remotes;
* restoring Atlas-owned local changes.

Remote publication or protected remote changes require user approval:

* push;
* PR creation;
* remote branch/tag publication;
* PR merge;
* protected remote state changes.

## Execution Rules

For each package:

1. Read the active package from `docs/atlas_twin_forge_git_steward_goal_mode_execution.md` and current status.
2. Verify the current implementation against actual code before editing.
3. Reproduce or prove the reviewed gap with a failing or missing test where practical.
4. Implement the smallest coherent vertical slice.
5. Preserve all authority boundaries.
6. Preserve off / shadow / active rollout behavior where applicable.
7. Run focused tests, affected tests, syntax checks, and available runtime/model evidence.
8. Record unavailable checks truthfully.
9. Update `docs/atlas_twin_forge_git_steward_current_status.md`.
10. Advance only when acceptance criteria pass.

## Evidence Rules

Every completed package must record:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Atlas UI evidence:
Project Intelligence evidence:
Runtime/Portal evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

Use LLMs for review and comparative evaluation only as advisory evidence. Mechanical tests, deterministic graph assertions, real provider calls, Portal runtime behavior, Capsule replay, and rollback drills are authoritative.

## Stop Conditions

Stop only for:

* destructive migration requiring explicit approval;
* changing default external-code exposure;
* deleting legacy model execution paths;
* safety or authority conflict with Proposal / Safe Apply / Verification;
* required live model/runtime/web evidence unavailable with no truthful alternative;
* security issue involving credentials, external providers, package import, runtime execution, or generated artifacts.

## Completion

For Twin / Forge / Git Steward completion, use:

```text
docs/atlas_twin_forge_git_steward_goal_mode_execution.md
docs/atlas_twin_forge_git_steward_current_status.md
```

Do not mark the active goal complete until the goal-mode final acceptance criteria pass, including contract tests, integration tests, adversarial tests, shadow evidence, active gated rollout, and real LLM/runtime evidence or truthful unavailable records.
