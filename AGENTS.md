# KasaneCore Agent Instructions

## Active Goal

The current active track is **Forge / Twin / Arena / Anvil 統合改修 — Phase 2: 弱 LLM 補強の完成形** (Method layer is in place; remaining work hardens it to real-model maturity).

**START HERE — read this one file first, it is self-sufficient to begin:**

```text
docs/forge_twin_arena_anvil_integration_agent_entrypoint.md
```

It contains: the read order, the per-item PR workflow, the verified test command, the hard invariants, the `decomposition_policy.py` naming-collision warning, and the existing foundation to reuse. Supporting docs:

1. `docs/forge_twin_arena_anvil_integration_plan.md` — living plan + PR breakdown + progress tracker (update before/after each item). **The extended "Phase 2" PR table (PR16–PR22) is the authoritative remaining-work list.**
2. `docs/forge_twin_arena_anvil_integration_current_status.md` — Phase 0 inventory / component classification + per-PR completion proofs.

**Current state (HEAD `91e07e32`):** PR1–PR15 are merged (MethodVariant / MethodAdapter / MethodRegistry / MethodPipeline / MethodRouter, schema ext, adapters, eval dimensions, evaluation + twin-facade API, real LLM runner, optimizer/loadout, Arena radar / fallback graph / method comparison UI, Advanced Twin inspector, Atlas method shadow). The Method-layer skeleton exists but is **not yet the "weak-LLM reinforcement completed form."**

**Remaining work (each item = 1 PR, branch + implement + test + PR + merge):**

- **PR16 `feat/forge-anvil-real-eval` (P0, NEXT):** formal Anvil acceptance — start Anvil, `/models/db` → `/model/switch` → `/model/status` ready → `/v1/models`, run `/api/forge/evaluation/run-live`, exercise structured/edit-intent/anchor/fallback/evidence cases, capture **natural** fallback evidence. Add proof level `anvil_real_eval_passed`; until then `anvil_real_eval_pending`, never `acceptance_complete`.
- **PR17 `feat/forge-natural-fallback-pack` (P0):** real-model natural fallback cases (schema_invalid / patch_apply_failure / anchor_not_found / content_missing / file_changes_missing / unsafe_path / provider_unavailable) — not forced.
- **PR18 `feat/forge-method-router-v2` (P1):** expand MethodRouter rules + policy enums (still never overrides RouteMatrix).
- **PR19 `feat/forge-multimodel-roleassignment` (P1):** multi-model planner/implementer/verifier/repairer/reviewer/fallback assignment + live eval-dimension expansion.
- **PR20 `feat/forge-active-execution-gated` (P1):** gated active execution behind explicit confirmation; Proposal / Safe Apply / Verification always preserved; active automation default OFF.
- **PR21 `feat/forge-frontier-eval-verification` (verification):** for **all** benchmark dimensions, verify the **8080 weak-LLM (Qwen3.6-35B-A3B)** evaluation output with a **frontier model**; mismatches recorded as `frontier_verification_mismatch` (never upgraded to passed). Then run the benchmark end-to-end to confirm the evaluation path is sound.
- **PR22 `feat/forge-atlas-route-validation` (verification):** using the optimal route + Twin injection level derived from Forge model-benchmark results, validate Atlas planning / code development / completion in shadow without changing production routing.

**Standing authorization:** the user has explicitly authorized creating and merging a PR per item for this track (2026-06-21; reaffirmed for Phase 2). Do not replace existing modules — integrate/extend. Test command: `venv_sys/Scripts/python.exe -m pytest -q tests/<file>.py`.

**Evaluation policy for this track:** run evaluations against the local **8080 weak LLM**; treat weak-LLM judgments as advisory and verify them with a frontier model (PR21). `unavailable` is never `passed`; mock/synthetic is never real evidence. Focused tests alone do not justify `acceptance_complete`.

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
