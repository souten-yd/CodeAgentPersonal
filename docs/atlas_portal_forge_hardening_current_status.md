# Atlas Portal + Model Forge Hardening — Current Status

> Mutable checkpoint for Codex / Claude Goal mode.
> Update after every coherent PFH package.

## Program state

- Overall: **ACTIVE — POST-PFG PRODUCTION HARDENING**
- Active track: `PFH-1..PFH-8`
- Current package: `PFH-1`
- Current package goal: fix benchmark preset identity and execution semantics.
- Rollout: Forge remains off/default unless bridge-level shadow/cutover evidence proves otherwise.
- Legacy model execution remains primary until PFH-4/PFH-5 evidence passes.
- OpenRouter live evidence remains unavailable unless explicitly configured.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_portal_forge_current_status.md`
3. `docs/atlas_portal_forge_hardening_current_status.md`
4. `docs/atlas_portal_forge_hardening_plan.md`
5. current PFH package in the hardening plan
6. `docs/atlas_portal_forge_hardening_test_plan.md`
7. `docs/atlas_portal_forge_hardening_agent_entrypoint.md`
8. relevant Portal Forge design/test/current-status docs
9. target code, public contracts, direct callers, dependencies, and tests

## Package table

| Package | Goal | Status |
|---|---|---|
| PFH-1 | Benchmark preset identity and execution semantics | in_progress |
| PFH-2 | OpenRouter catalog product integration | not_started |
| PFH-3 | Provider configured state vs runtime readiness | not_started |
| PFH-4 | ForgeModelExecutionBridge, shadow-first | not_started |
| PFH-5 | Real cutover and rollback | not_started |
| PFH-6 | Real evidence through Forge provider/preset runner | not_started |
| PFH-7 | Actual Portal runtime replay for Capsule evidence | not_started |
| PFH-8 | Guarded Candidate-to-Proposal handoff | not_started |

## Known review findings to address

```text
1. Forge cutover updates StageMatrix policy but does not yet prove the actual Atlas model execution data path is switched.
2. LegacyAtlasProvider is not wired as a live ForgeService execution backend for current Atlas calls.
3. OpenRouterCatalog exists but is not fully product-connected to ForgeService/API/UI model selection.
4. Benchmark UI primary preset IDs can diverge from real backend preset IDs.
5. Benchmark run can submit only the first selected preset.
6. Some real evidence tests use direct urllib model calls rather than Forge provider/preset runner path.
7. Local provider health can be misleading if base_url exists but server is unreachable.
8. Capsule replay evidence should be actual Portal/Play runtime evidence where applicable, not caller assertion only.
```

## Evidence requirements

For each package, record:

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
OpenRouter evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

## Current package: PFH-1 checklist

- Inspect `agent/model_forge/benchmark_presets.py`.
- Inspect Forge API preset listing.
- Inspect `web/js/forge.js` benchmark primary preset selection and run payload.
- Replace fake hard-coded primary IDs with backend-derived real preset IDs or explicit family aliases.
- Update tests to consume real preset listing shape.
- Ensure multi-selected presets are sent to backend or explicitly unavailable.
- Update this status with exact evidence.

## Stop conditions

Stop only for:

- destructive migration requiring explicit approval;
- changing default external-code exposure;
- removing legacy model execution path;
- safety/authority conflict with Proposal/Safe Apply/Verification;
- required live model/OpenRouter/Portal runtime unavailable with no truthful alternative.
