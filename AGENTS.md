# KasaneCore Agent Instructions

## Active Goal

* Atlas Portal + Model Forge Hardening
* Current status: `docs/atlas_portal_forge_hardening_current_status.md`
* Main plan: `docs/atlas_portal_forge_hardening_plan.md`
* Test plan: `docs/atlas_portal_forge_hardening_test_plan.md`
* Agent entrypoint: `docs/atlas_portal_forge_hardening_agent_entrypoint.md`

## Completed Foundations

PIR and PFG are completed foundation tracks. Do not restart them from scratch.

* PIR: completed Project Intelligence Recovery foundation and evidence docs are retained.
* PFG: completed Portal + Model Forge foundation and evidence docs are retained.
* Portal / Play / Capsule foundation is already implemented; do not rebuild Portal from zero.
* Forge foundation exists, but the hardening track must verify and complete production data-plane integration.

Retained reference docs include:

```text
docs/atlas_project_intelligence_recovery_current_status.md
docs/atlas_project_intelligence_recovery_master_goal.md
docs/atlas_portal_forge_current_status.md
docs/atlas_portal_forge_master_goal.md
docs/atlas_portal_forge_detailed_design.md
docs/atlas_portal_forge_implementation_plan.md
docs/atlas_portal_forge_test_plan.md
```

## Current Hardening Objective

Convert the existing Forge control plane into a production-connected, evidence-driven model execution path.

The main known gap is:

```text
Forge cutover must affect the actual Atlas model execution boundary,
not only StageMatrix policy or UI state.
```

The hardening track must prove:

```text
legacy primary
-> Forge shadow
-> Forge primary with legacy fallback
-> rollback to legacy primary
```

using real code paths, tests, and evidence.

## Must Preserve

* `unavailable` is not `passed`.
* Mock results are not live evidence.
* UI rendering is not runtime evidence.
* Adapter-only tests are not production integration.
* Arena candidates must not bypass Proposal / Safe Apply / Verification.
* Portal owns runtime, artifact, and generated-data lifecycle.
* Forge owns model, provider, route, benchmark, Arena, and profile selection.
* Atlas owns requirement, plan, proposal, Safe Apply, verification, repair, and convergence.
* External providers are disabled by default and policy-gated.
* Local Only mode must not call OpenRouter or any external provider.
* OpenRouter live evidence requires `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY`.
* Secrets must never be persisted, logged, or returned by API.
* Capsule package ZIPs must remain immutable and data-free by default.
* Legacy model paths must not be deleted until consumer-zero, benchmark, shadow, rollback, and migration gates pass.

## Goal Mode Read Order

1. `AGENTS.md`
2. `docs/atlas_portal_forge_hardening_current_status.md`
3. `docs/atlas_portal_forge_hardening_plan.md`
4. `docs/atlas_portal_forge_hardening_test_plan.md`
5. `docs/atlas_portal_forge_hardening_agent_entrypoint.md`
6. Existing PFG docs when touching Forge / Portal / Capsule
7. Existing PIR docs when touching Atlas / PlanPool / Proposal / Safe Apply / Verification / Convergence
8. Target code, public contracts, direct callers, dependencies, and tests

## Execution Rules

For the current PFH package:

1. Read the selected package from `docs/atlas_portal_forge_hardening_current_status.md`.
2. Verify the current implementation against actual code before editing.
3. Reproduce or prove the reviewed gap with a failing or missing test where practical.
4. Implement the smallest coherent vertical slice.
5. Preserve all authority boundaries.
6. Run focused tests, affected tests, syntax checks, and runtime/model evidence where required.
7. Record unavailable checks truthfully.
8. Update `docs/atlas_portal_forge_hardening_current_status.md`.
9. Advance to the next PFH package only when acceptance criteria pass.

## Active Package Sequence

```text
PFH-1: Benchmark preset identity and execution semantics
PFH-2: OpenRouter catalog product integration
PFH-3: Provider configured state vs runtime readiness
PFH-4: ForgeModelExecutionBridge, shadow-first
PFH-5: Real cutover and rollback
PFH-6: Real evidence through Forge provider/preset runner
PFH-7: Actual Portal runtime replay for Capsule evidence
PFH-8: Guarded Candidate-to-Proposal handoff
```

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
Portal runtime evidence:
Capsule replay evidence:
OpenRouter evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

Use LLMs for review and comparative evaluation only as advisory evidence. Mechanical tests, real provider calls, Portal runtime behavior, Capsule replay, and rollback drills are authoritative.

## Stop Conditions

Stop only for:

* destructive migration requiring explicit approval;
* changing default external-code exposure;
* deleting legacy model execution paths;
* safety or authority conflict with Proposal / Safe Apply / Verification;
* required live model, OpenRouter, or Portal runtime unavailable with no truthful alternative;
* security issue involving credentials, external providers, package import, or runtime execution.

Implementation size alone is not a stop condition.

## Completion

Do not mark Portal + Model Forge Hardening complete until:

* PFH-1 through PFH-8 are `acceptance_complete` or explicitly deferred with truthful evidence;
* Forge model execution is connected to the actual Atlas model execution boundary in shadow mode;
* at least one stage has a tested, reversible Forge-primary cutover path with legacy fallback;
* real evidence tests run through the Forge provider, preset runner, or execution bridge;
* Capsule replay profile updates are based on actual Portal or Play runtime evidence;
* OpenRouter catalog is product-connected without secrets and without false live-evidence claims.
