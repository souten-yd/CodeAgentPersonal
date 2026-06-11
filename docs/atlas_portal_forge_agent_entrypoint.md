# Atlas Portal + Model Forge — Agent Entrypoint

Use this file as the Goal-mode entrypoint for implementing the Portal + Model Forge program.

## Goal prompt

```text
Read AGENTS.md first.

Execute the Atlas Portal + Model Forge goal through completion in KasaneCore.

Use these canonical files in order:
1. AGENTS.md
2. docs/atlas_portal_forge_master_goal.md
3. docs/atlas_portal_forge_current_status.md
4. current package in docs/atlas_portal_forge_implementation_plan.md
5. relevant sections of docs/atlas_portal_forge_detailed_design.md
6. relevant sections of docs/atlas_portal_forge_test_plan.md
7. Portal/Capsule baseline docs when touching Portal:
   - docs/atlas_play_portal_capsule_current_status.md
   - docs/atlas_play_portal_capsule_goal.md
   - docs/atlas_capsule_portal_spec.md
8. Project Intelligence Recovery docs when touching Atlas/PlanPool/Proposal/Safe Apply/Verification/Convergence:
   - docs/atlas_project_intelligence_recovery_current_status.md
   - docs/atlas_project_intelligence_recovery_master_goal.md

Important current facts:
- Portal / Play / Capsule PR-PPC-0 through PR-PPC-12 are already complete.
- Portal UI reconciliation already added the Portal nav, Portal run sheet, Save/Snapshot/Discard, Export, Fork, Uninstall, Delete Data, and Capsule builder UI.
- Do not restart Portal from scratch.
- Complete only the remaining Portal polish gaps: upload import, snapshot selector, legacy manifest sidecar repair, and Forge Trace integration.
- Forge is a new model/provider/route evaluation and selection system.
- OpenRouter is one Forge Provider, not a special hard-coded execution path.
- The legacy model execution/orchestration path must be wrapped as a Legacy Executor and kept as primary until shadow/cutover evidence passes.
- Do not delete legacy model paths before retirement gates.
- Do not claim live model, OpenRouter, Portal runtime, benchmark, or cutover evidence unless it actually ran.
- Unavailable is not passed.
- Arena candidates must never be applied directly. Candidate adoption must go through Proposal, Safe Apply, Verification, and when runnable, Portal.
- External model usage must obey Source Mode and privacy policy. Local Only must not call OpenRouter or any external provider.
- UI must remain simple, modern, mobile-friendly, and advanced controls must be collapsible.

Implementation loop:
1. Read the current package selected by docs/atlas_portal_forge_current_status.md.
2. Verify the package against current code before editing.
3. Implement the smallest coherent vertical slice for that package.
4. Preserve existing Portal, Atlas, PIR, PlanPool, Proposal, Safe Apply, Verification, and Convergence authority boundaries.
5. Add focused tests and affected tests.
6. Run syntax checks and relevant suites.
7. Run real Portal/model/OpenRouter evidence only when the package requires it and the environment is available.
8. Record unavailable checks truthfully.
9. Update docs/atlas_portal_forge_current_status.md with exact evidence and proof level.
10. Advance to the next package when acceptance passes.
11. Continue automatically until PFG-38 acceptance_complete or a real stop condition occurs.

Stop only for:
- destructive migration requiring explicit approval;
- safety/authority conflict;
- required environment unavailable with no truthful alternative;
- security/privacy decision that changes external-code exposure defaults;
- broad legacy deletion before retirement evidence.

Do not stop merely because the implementation is large or spans many PRs.
```

## PR discipline

Each PR should be a coherent package or sub-package. Do not bundle unrelated Portal UI, provider, Arena, and retirement work in one PR unless the current package explicitly requires it.

Every PR must update `docs/atlas_portal_forge_current_status.md`.

Every PR description should include:

```text
Summary
Tests / Evidence
Unavailable checks
Safety invariants
Rollout / migration state
Next package
```

## Required evidence style

Use exact commands and results.

Good:

```text
python -m pytest -q tests/test_model_forge_provider_registry.py -> 12 passed in 0.41s
OpenRouter live smoke unavailable: FORGE_OPENROUTER_LIVE_SMOKE not set; no external request made.
```

Bad:

```text
Tests passed.
OpenRouter works.
Portal should run.
```

## UI expectations

Default UI should show:

```text
Forge Overview
  Active Loadout
  Source Mode
  Provider Health
  Champions
  Recent Arena

Advanced
  Stage Matrix
  Route Matrix
  Raw profile details
```

Portal should show a compact Forge Trace only when trace exists. Legacy Portal runs without trace must still load cleanly.

## Completion checklist

The program is not complete until:

- PFG-0 through PFG-38 are acceptance_complete or explicitly deferred by a documented decision;
- Portal polish gaps are closed or truthfully deferred;
- Forge schemas/providers/presets/Arena/evaluator/profile/selector/UI exist;
- OpenRouter is safe, disabled by default, mock-tested, and optionally live-smoked;
- Portal run and Capsule replay feed Forge profile evidence;
- at least Quick, Web App, Repair, and Greenfield have real local/self-hosted model evidence when available;
- selected stages have shadow evidence before Forge primary;
- any legacy retirement has consumer-zero, benchmark, migration, rollback, and real evidence.
