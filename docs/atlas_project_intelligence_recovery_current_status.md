# Atlas Project Intelligence Recovery — Current Status

## Program state

- Overall: **ACTIVE — PRODUCTION LOOP INCOMPLETE**
- Foundation Track: `PI-0..PI-25` merged as contracts, components, and scaffolds
- Active corrective track: `PIR-0..PIR-15`
- Current package: `PIR-1`
- Next action: implement durable concrete module foundations behind the public facades
- Blocker: none
- Rollout: off by default

This file selects the active package. The old PI package table does not prove final completion.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_recovery_master_goal.md`
3. `docs/atlas_project_intelligence_pi0_25_implementation_audit.md`
4. this file
5. current package in `docs/atlas_project_intelligence_recovery_implementation_plan.md`
6. relevant recovery detailed-design and test-plan sections
7. existing Project Intelligence decisions, contracts, and architecture
8. target code, direct callers, dependencies, and tests

## Confirmed gaps

- production composition uses disabled modules;
- coordinator active paths do not return real module output;
- concrete Twin and Convergence facades are missing;
- new Planner, Generator, and Verification adapters are not connected to real Atlas consumers;
- durability defects remain in Blueprint, event projection, and checkpoints;
- CFG, data flow, frontend semantics, and resource graphs are incomplete;
- Convergence revision and completion logic require correction;
- Plan Compiler is not authoritative PlanPool integration;
- Greenfield E2E and final benchmark are synthetic;
- live rollout, platform evidence, consumer cutover, and retirement are incomplete.

## Package table

| Package | Goal | Status |
|---|---|---|
| PIR-0 | baseline, inventory, regression locks | acceptance_complete |
| PIR-1 | durable concrete modules | not_started |
| PIR-2 | production composition and rollout preflight | not_started |
| PIR-3 | source snapshots and Twin refresh | not_started |
| PIR-4 | durable event and delivery integration | not_started |
| PIR-5 | verification ingest, context, impact, test selection | not_started |
| PIR-6 | whole-project semantic graph | not_started |
| PIR-7 | CFG, data flow, state/event/resource graphs | not_started |
| PIR-8 | durable Blueprint planning and review | not_started |
| PIR-9 | Convergence correctness and evidence policy | not_started |
| PIR-10 | Planner and PlanPool production integration | not_started |
| PIR-11 | Proposal, Safe Apply, and refresh integration | not_started |
| PIR-12 | Verification, recovery, checkpoint, resume | not_started |
| PIR-13 | real Greenfield E2E | not_started |
| PIR-14 | CI, platform, scale, and consumer cutover | not_started |
| PIR-15 | real benchmark and retirement | not_started |

## Status values

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Do not use plain `Completed` without the proof level. Focused tests alone cannot close a package requiring production or live evidence.

## Completion rule

The program remains incomplete until PIR-15 and every live Definition of Done gate in the recovery master goal pass. Synthetic runners, manually supplied metrics, adapter-only tests, and document statements are not production evidence.

## Executed package log

```text
Work package: PIR-0 — Truthful baseline, executable inventory, and regression locks
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/inspection/consumer_inventory.py — AST-based production entrypoint,
  legacy consumer, facade/adapter, construction-site, module implementation, and persistence
  default inventory generator.
- tools/generate_project_intelligence_consumer_inventory.py — CLI for regenerating the inventory.
- docs/generated/atlas_project_intelligence_consumer_inventory.json — generated artifact from
  the current checkout.
- tests/test_project_intelligence_recovery_baseline.py — PIR-0 inventory assertions plus strict
  xfail regression locks for audited defects PIR0-C01..PIR0-C07.
- docs/atlas_project_intelligence_current_status.md — PI-0..PI-25 reframed as Foundation Track.
Executed commands and exact results:
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=31 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m py_compile agent/project_intelligence/inspection/consumer_inventory.py
  tools/generate_project_intelligence_consumer_inventory.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  5 passed, 6 xfailed in 16.30s
- python -m pytest -q tests/test_project_intelligence_baseline.py
  tests/test_project_intelligence_contracts.py tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_recovery_baseline.py -> 74 passed, 6 xfailed in 18.44s
- $files = Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName };
  python -m pytest -q @files -> 291 passed, 6 xfailed in 30.20s
Unavailable checks: none for PIR-0; no production behavior change or live environment claim.
Safety invariants checked: read-only source inspection only; no production runtime, PlanPool,
  Proposal, Safe Apply, verification, rollout, or legacy path behavior changed.
Migration/rollout state: off by default; no consumer cutover and no legacy deletion.
Known limitations: regression locks intentionally xfail until PIR-1+ fixes the underlying defects.
Next package: PIR-1 — durable concrete modules.
Blocker: none.
```
