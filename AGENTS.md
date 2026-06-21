# KasaneCore Agent Instructions

## Active Goal

The current active track is **Forge Twin Assist Evaluation — Atlas実生成補助評価・弱LLM補助レベル最適化**.

**START HERE — read this one file first, it is self-sufficient to begin:**

```text
docs/forge_twin_arena_anvil_integration_agent_entrypoint.md
```

That entrypoint routes the implementation to the active continuation plans:

```text
docs/forge_twin_assist_evaluation_plan.md
docs/forge_twin_assist_readiness_extension_plan.md
```

## Current State

The previous Forge / Twin / Arena / Anvil track has progressed through PR16–PR22 and H1–H4. The Method layer, Anvil real eval, natural fallback pack, MethodRouter v2, multi-model role assignment, active gate, Atlas route validation, semantic hardening, full-axis frontier verification, and capability rescue policy are present.

The next gap is not another model-only benchmark. The next gap is to evaluate the **effective Atlas code generation path** with and without Twin injection:

- baseline: Atlas patch generation with no Twin assist;
- assisted: Atlas patch generation with policy/constraints/refs/impact/Safe-Edit/strict TwinBrief/Twin-localized slot/deterministic anchor;
- compare score, lift, harm, latency, token usage, forbidden touches, semantic validation, verification plan, and evidence refs;
- record model-specific recommended Twin assist mode, injection level, avoided methods, and fallback chain;
- wire recommendations into ProfileStore, MethodRouter, and ExecutionPolicy without changing production routing automatically.

After TA1–TA8, continue into TA9–TA12 to evaluate the **Twin implementation readiness**, route/method/assist matrix, slot quality gates, and post-apply E2E behavior.

## Authoritative Plans

1. `docs/forge_twin_assist_evaluation_plan.md` — TA1–TA8: baseline vs assisted Twin Assist evaluation.
2. `docs/forge_twin_assist_readiness_extension_plan.md` — TA9–TA12: Twin readiness, route-method-assist matrix, slot quality gates, post-apply E2E.

Supporting historical docs:

1. `docs/forge_twin_arena_anvil_integration_plan.md` — living plan through PR16–PR22 and H1–H4.
2. `docs/forge_twin_arena_anvil_integration_current_status.md` — component inventory and per-PR completion proofs.
3. `docs/forge_twin_arena_anvil_integration_agent_entrypoint.md` — read order and execution workflow.

## Next Work Items

Execute the following packages in order, one coherent PR per item unless the user explicitly requests direct write-only changes:

| # | Branch | Goal | Status |
|---|---|---|---|
| TA1 | `feat/forge-twin-assist-contracts` | Add TwinAssistMode taxonomy, DTOs, strict schema tests | pending |
| TA2 | `feat/forge-twin-assist-packs` | Add Twin Assist case packs, fixtures, scoring, harm detection | pending |
| TA3 | `feat/forge-twin-assist-runner` | Run baseline vs assisted through `AtlasPatchProposalService.propose_for_item` | pending |
| TA4 | `feat/forge-twin-localized-slot` | Add TwinEditSlot resolver and slot patch adapter MVP | pending |
| TA5 | `feat/forge-twin-assist-policy` | Connect recommendations to MethodRouter / ExecutionPolicy / ProfileStore | pending |
| TA6 | `feat/forge-twin-assist-api` | Add `/api/forge/twin-assist/*` APIs | pending |
| TA7 | `feat/forge-twin-assist-ui` | Add Forge UI Twin Assist tab / result drawer / profile recommendation | pending |
| TA8 | `feat/forge-twin-assist-real-eval` | Run 8080 real-model evaluation and record evidence | pending |
| TA9 | `feat/forge-twin-readiness-score` | Evaluate Twin snapshot/freshness/symbol/impact/Safe-Edit/prompt delivery readiness | pending |
| TA10 | `feat/forge-route-method-assist-matrix` | Evaluate route × method × assist × fallback matrix | pending |
| TA11 | `feat/forge-twin-slot-quality-gates` | Add slot/anchor/range quality gates and confidence calibration | pending |
| TA12 | `feat/forge-twin-assist-postapply-e2e` | Evaluate proposal→Safe Apply dry-run→focused tests→post-apply Twin gate | pending |

## Standing Authorization

The user has explicitly authorized writing these plans into the project and continuing from the current plan state. For implementation PRs, keep the existing per-item workflow unless the user explicitly asks for a direct commit. Remote publication / PR creation / merge remain approval-bound outside the already-authorized track.

## Must Preserve

* `unavailable` is not `passed`.
* Mock results are not live evidence.
* UI rendering is not runtime evidence.
* Inferred graph facts are not verified facts.
* Twin Assist Evaluation must not directly apply files.
* Project Intelligence and Twin are advisory context/evidence, not execution authority.
* Atlas owns requirement, PlanPool, Proposal, Safe Apply, Verification, Repair, and Convergence.
* Portal owns runtime execution, artifact lifecycle, generated-data save/discard, and Capsule replay.
* Forge owns model/provider/profile routing and benchmark evidence.
* Nexus owns external web research. External/web calls remain policy-gated and disabled by default.
* No code path may bypass Proposal / Safe Apply / Verification.
* No external provider may run in Local Only mode.
* Secrets must never be persisted, logged, returned by API, embedded in Capsule ZIPs, or included in Project Intelligence stores.
* Capsule package ZIPs must remain immutable and data-free by default.
* Implementation size alone is not a stop condition.
* Twin-assist recommendations are observations/recommendations only; active routing still goes through the existing gated activation/cutover policy.
* Twin injection harm must be recorded honestly when assisted generation is worse than baseline.
* Twin readiness must cap advanced assist modes when the Project Twin is stale, unavailable, or low-confidence.
* Slot-based assist must never use non-unique anchors, forbidden refs, broad ranges, or direct apply.
* Post-apply E2E evaluation must run only in isolated workspace / dry-run / rollback-capable flows.

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

1. Read the active package from `docs/forge_twin_assist_evaluation_plan.md` for TA1–TA8 or `docs/forge_twin_assist_readiness_extension_plan.md` for TA9–TA12.
2. Verify the current implementation against actual code before editing.
3. Reproduce or prove the gap with a failing or missing test where practical.
4. Implement the smallest coherent vertical slice.
5. Preserve all authority boundaries.
6. Preserve off / shadow / active rollout behavior where applicable.
7. Run focused tests, affected tests, syntax checks, and available runtime/model evidence.
8. Record unavailable checks truthfully.
9. Update the active plan doc and `docs/forge_twin_arena_anvil_integration_current_status.md` when a package completes.
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
Baseline score:
Assisted score:
Lift:
Harm cases:
Best assist mode:
Twin readiness score:
Readiness level:
Symbol resolution rate:
Impact precision:
Safe-Edit Briefing availability:
Prompt delivery audit:
Route-method-assist matrix best candidate:
Slot quality score:
Slot blocked reasons:
Post-apply apply status:
Focused tests:
Post-apply Twin gate:
Proof ledger ref:
Rollback evidence:
E2E lift:
E2E harm:
Profile recommendation:
Atlas UI evidence:
Project Intelligence evidence:
Runtime/Portal evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
Proof level:
```

Use LLMs for review and comparative evaluation only as advisory evidence. Mechanical tests, deterministic graph assertions, real provider calls, Portal runtime behavior, Capsule replay, and rollback drills are authoritative.

## Stop Conditions

Stop only for:

* destructive migration requiring explicit approval;
* changing default external-code exposure;
* deleting legacy model execution paths;
* safety or authority conflict with Proposal / Safe Apply / Verification;
* required live model/runtime/web evidence unavailable with no truthful alternative;
* security issue involving credentials, external providers, package import, runtime execution, or generated artifacts;
* readiness unavailable being treated as trusted;
* non-unique anchor being accepted for slot assist;
* direct workspace apply during evaluation;
* focused tests unavailable being marked passed;
* RouteMatrix-unsafe candidate being selected as matrix winner.

## Completion

For the active Twin Assist Evaluation goal, use:

```text
docs/forge_twin_assist_evaluation_plan.md
docs/forge_twin_assist_readiness_extension_plan.md
docs/forge_twin_arena_anvil_integration_current_status.md
```

Do not mark the active goal complete until the final acceptance criteria pass, including baseline/assisted comparison, lift/harm recording, Twin readiness scoring, route-method-assist matrix, slot quality gates, ProfileStore recommendation, MethodRouter/ExecutionPolicy integration, UI evidence, post-apply E2E evidence, and real 8080 model evidence or truthful unavailable records.
