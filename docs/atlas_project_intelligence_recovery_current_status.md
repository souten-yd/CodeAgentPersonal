# Atlas Project Intelligence Recovery — Current Status

## Program state

- Overall: **ACTIVE — PRODUCTION LOOP INCOMPLETE**
- Foundation Track: `PI-0..PI-25` merged as contracts, components, and scaffolds
- Active corrective track: `PIR-0..PIR-15`
- Current package: `PIR-0`
- Next action: generate the real production-consumer inventory and add regression locks for the audit findings
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
| PIR-0 | baseline, inventory, regression locks | not_started |
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
