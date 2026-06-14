# KasaneCore Agent Instructions

## Active Goal

* Atlas Runtime Progress, Resume/Rehydrate, and Project Intelligence Behavioral Impact Hardening
* Current status: `docs/atlas_runtime_progress_resume_hardening_current_status.md`
* Main plan: `docs/atlas_runtime_progress_resume_hardening_plan.md`
* Test plan: `docs/atlas_runtime_progress_resume_hardening_test_plan.md`
* Agent entrypoint: `docs/atlas_runtime_progress_resume_hardening_agent_entrypoint.md`
* Next track after AUIR: `docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md`

## Track Order

The current user-reported Atlas bug blocks safe development visibility. Therefore complete AUIR first, then continue PIBIH.

```text
AUIR-1: Fix LLM props initialization and token indicator safety
AUIR-2: Durable Atlas run progress event model
AUIR-3: Atlas tab reload/resume rehydration
AUIR-4: Live indicator reconnection and stale/stalled state UX
AUIR-5: Regression tests and mobile/browser reload smoke
AUIR-6: Return to PIBIH-1 LLM planning timeout hardening

PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening
PIBIH-2: Impact Analysis Core
PIBIH-3: Deep Behavioral Graph V3
PIBIH-4: Project Intelligence Planning and Generation Injection
PIBIH-5: Plan-Time Nexus Web Research
PIBIH-6: Impact UI / Planner Exposure
PIBIH-7: Runtime Evidence Promotion and Historical Risk Memory
```

## Current Blocking Bug

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

## Completed Foundations

PIR, PFG, Portal, Play, Capsule, Forge foundation, and prior Portal/Forge hardening are completed foundation tracks. Do not restart them from scratch.

Retain and reference these docs as needed:

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
```

The two new handoff tracks are:

```text
docs/atlas_runtime_progress_resume_hardening_current_status.md
docs/atlas_runtime_progress_resume_hardening_plan.md
docs/atlas_runtime_progress_resume_hardening_test_plan.md
docs/atlas_runtime_progress_resume_hardening_agent_entrypoint.md

docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
docs/atlas_project_intelligence_behavioral_impact_hardening_plan.md
docs/atlas_project_intelligence_behavioral_impact_hardening_test_plan.md
docs/atlas_project_intelligence_behavioral_impact_hardening_agent_entrypoint.md
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

## Goal Mode Read Order

1. `AGENTS.md`
2. `docs/atlas_runtime_progress_resume_hardening_current_status.md`
3. `docs/atlas_runtime_progress_resume_hardening_plan.md`
4. `docs/atlas_runtime_progress_resume_hardening_test_plan.md`
5. `docs/atlas_runtime_progress_resume_hardening_agent_entrypoint.md`
6. After AUIR completion, read:
   - `docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md`
   - `docs/atlas_project_intelligence_behavioral_impact_hardening_plan.md`
   - `docs/atlas_project_intelligence_behavioral_impact_hardening_test_plan.md`
   - `docs/atlas_project_intelligence_behavioral_impact_hardening_agent_entrypoint.md`
7. Existing PIR/PFG/PFH docs when touching their areas
8. Target code, public contracts, direct callers, dependencies, and tests

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

Do not mark the combined track complete until:

* `_current_n_ctx_ui` can never throw before initialization during startup, mode switch, reload, or settings/context polling;
* LLM progress indicators update during Plan, approved execution, patch proposal generation, repair, and verification-related LLM calls;
* browser tab switch and reload restore the active Atlas run status from server-authoritative state;
* a disconnected/reconnecting UI never shows an empty green frame without status;
* stale/stalled/live/terminal states are visibly distinct;
* slow local planning models can complete or fail with phase-specific timeout reasons;
* Impact Analysis returns direct/transitive impacts, side effects, recommended tests, and uncertainty for realistic fixture projects;
* Behavioral Graph V3 captures function, variable, state, resource, and UI/API paths with deterministic refs;
* Project Intelligence active planning and active generation both use rich context;
* Plan-time Nexus Web Research is bounded, gated, persisted, and reflected in planning when enabled;
* UI/PlanPool artifacts show impact summaries and recommended tests;
* runtime/verification evidence can feed future impact risk without false verification claims;
* all safety boundaries remain intact.
