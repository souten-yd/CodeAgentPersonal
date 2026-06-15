# KasaneCore Agent Instructions

## Default Start Point

Start from AUIR unless the user explicitly names another track.

AUIR is the current default goal:

* Current status: `docs/atlas_runtime_progress_resume_hardening_current_status.md`
* Main plan: `docs/atlas_runtime_progress_resume_hardening_plan.md`
* Test plan: `docs/atlas_runtime_progress_resume_hardening_test_plan.md`
* Agent entrypoint: `docs/atlas_runtime_progress_resume_hardening_agent_entrypoint.md`

After AUIR is complete, continue PIBIH:

* `docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md`
* `docs/atlas_project_intelligence_behavioral_impact_hardening_plan.md`
* `docs/atlas_project_intelligence_behavioral_impact_hardening_test_plan.md`
* `docs/atlas_project_intelligence_behavioral_impact_hardening_agent_entrypoint.md`

## Compact Goal Override: Twin / Forge / Git Steward

Use this only when the user explicitly asks for Twin / Forge / Git Steward work.

Keep `AGENTS.md` small and delegate to:

1. `docs/atlas_twin_forge_git_steward_goal_mode_execution.md`
2. `docs/atlas_twin_forge_git_steward_current_status.md`
3. `docs/atlas_twin_forge_git_steward_agent_entrypoint.md`
4. `docs/atlas_twin_forge_git_steward_detailed_plan.md` only when more detail is needed

Start from Package 0 in the goal-mode document. First run `python -m pytest -q tests/test_twin_forge_git_steward_initial.py`, repair type/import/pydantic/enum/module-path mismatches, record exact evidence in the current status doc, then continue the package sequence. Local Git operations are autonomous; remote publication still requires approval.

## Completed Foundations

PIR, PFG, Portal, Play, Capsule, Forge foundation, prior Portal/Forge hardening, and the Twin / Forge / Git Steward planning + initial policy slice are completed foundation tracks. Do not restart them from scratch.

Reference these only when touching their areas:

```text
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
docs/atlas_twin_forge_git_steward_current_status.md
docs/atlas_twin_forge_git_steward_goal_mode_execution.md
```

## AUIR Track Order

```text
AUIR-1: Fix LLM props initialization and token indicator safety
AUIR-2: Durable Atlas run progress event model
AUIR-3: Atlas tab reload/resume rehydration
AUIR-4: Live indicator reconnection and stale/stalled state UX
AUIR-5: Regression tests and mobile/browser reload smoke
AUIR-6: Return to PIBIH-1 LLM planning timeout hardening
```

## Current AUIR Bug

Observed behavior:

```text
Atlasでプラン生成後、承認して実行する。
その後開発を実行するが、LLMの生成状況がインジケータに表示されない。
インジケーターは停止している。

Log:
10:05:31 WARN [ctx] Could not fetch llm props: Cannot access '_current_n_ctx_ui' before initialization

別タブ移動やブラウザリロード後にAtlasへ戻ると、緑の枠だけ出てくる。
開発状況の表示やトークン生成のインジケータが一切表示されない。
```

Treat this as a product bug, not a cosmetic issue.

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

## Goal Mode Read Order

1. `AGENTS.md`
2. If the user explicitly names Twin / Forge / Git Steward, use the compact override above.
3. Otherwise read the AUIR docs listed in Default Start Point.
4. After AUIR completion, read the PIBIH docs listed above.
5. Existing PIR/PFG/PFH/TFG docs only when touching their areas.
6. Target code, public contracts, direct callers, dependencies, and tests.

## Execution Rules

For each package:

1. Read the selected package from the relevant current status doc.
2. Verify the current implementation against actual code before editing.
3. Reproduce or prove the reviewed gap with a failing or missing test where practical.
4. Implement the smallest coherent vertical slice.
5. Preserve all authority boundaries.
6. Preserve off / shadow / active rollout behavior where applicable.
7. Run focused tests, affected tests, syntax checks, and available runtime/model evidence.
8. Record unavailable checks truthfully.
9. Update the relevant current status doc.
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
Reload/resume evidence:
Project Intelligence evidence:
Impact analysis evidence:
Web research evidence:
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

Implementation size alone is not a stop condition.

## Completion

Do not mark AUIR complete until:

* `_current_n_ctx_ui` can never throw before initialization during startup, mode switch, reload, or settings/context polling;
* LLM progress indicators update during Plan, approved execution, patch proposal generation, repair, and verification-related LLM calls;
* browser tab switch and reload restore the active Atlas run status from server-authoritative state;
* a disconnected/reconnecting UI never shows an empty green frame without status;
* stale/stalled/live/terminal states are visibly distinct;
* all focused, affected, reload/resume, and mobile/browser smoke evidence is recorded;
* all safety boundaries remain intact.

After AUIR completion, continue PIBIH. For Twin / Forge / Git Steward completion, use `docs/atlas_twin_forge_git_steward_goal_mode_execution.md` and `docs/atlas_twin_forge_git_steward_current_status.md` only when that track is explicitly selected.
