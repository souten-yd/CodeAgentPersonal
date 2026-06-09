# Atlas Project Digital Twin Current Status

> Mutable checkpoint for Codex/Claude goal execution.  
> Update after every work package.  
> Do not infer completion from planning documents.

## Goal status

- Overall: PDT-1 completed
- Canonical goal: `docs/atlas_project_digital_twin_goal.md`
- Architecture: `docs/atlas_project_digital_twin_architecture.md`
- Contracts: `docs/atlas_project_digital_twin_contracts.md`
- Implementation plan: `docs/atlas_project_digital_twin_implementation_plan.md`
- Agent entrypoint: `docs/atlas_project_digital_twin_agent_entrypoint.md`
- Current work package: `PDT-2`
- Next action: Local transactional Twin Store (SQLite behind `ProjectTwinPort`)
- Blocker: None recorded
- Safety posture: Existing Atlas authority and verification rules unchanged

## Work package table

| WP | Title | Status | PR/Commit | Executed evidence |
|---|---|---|---|---|
| PDT-0 | Baseline and boundary inventory | Completed | pdt-0-baseline-inventory | `pytest -q tests/test_project_twin_baseline.py` -> 21 passed |
| PDT-1 | Versioned contracts | Completed | pdt-1-versioned-contracts | `pytest -q tests/test_project_twin_contracts.py` -> 23 passed; baseline -> 21 passed |
| PDT-2 | Local transactional Twin Store | Not started | — | — |
| PDT-3 | Static Structural Graph | Not started | — | — |
| PDT-4 | Intent and Delivery Trace | Not started | — | — |
| PDT-5 | Minimal Context Broker | Not started | — | — |
| PDT-6 | Memory integration | Not started | — | — |
| PDT-7 | Skill integration | Not started | — | — |
| PDT-8 | Behavioral Graph | Not started | — | — |
| PDT-9 | Runtime collectors | Not started | — | — |
| PDT-10 | Static/runtime reconciliation | Not started | — | — |
| PDT-11 | Impact and path analysis | Not started | — | — |
| PDT-12 | Nexus integration | Not started | — | — |
| PDT-13 | Project Twin API and UI | Not started | — | — |
| PDT-14 | E2E benchmark and rollout | Not started | — | — |

## PDT-0 required inventory

Inspect current code and tests for:

- repository indexing;
- symbol and dependency extraction;
- call graph or reference graph;
- API route discovery;
- related-test discovery;
- ContextBuilder and prompt-context injection;
- project investigation;
- requirement tracing;
- PlanPool/PlanItem/proposal/run/verification storage;
- browser/Playwright/Atlas Play observations;
- Runtime Trace or Behavior Graph code;
- `HybridMemoryStore`;
- Skill discovery and loading;
- Nexus evidence;
- Conversation/AgentSession persistence;
- graph or visualization components.

## PDT-0 outputs

Create:

```text
docs/atlas_project_digital_twin_baseline_inventory.md
tests/test_project_twin_baseline.py
```

The inventory must include:

- current capability;
- authoritative owner;
- relevant files and symbols;
- known duplication;
- reusable contracts;
- missing behavior;
- migration risk;
- test evidence;
- proposed PDT package destination.

## Resume protocol

1. Read `AGENTS.md`.
2. Read the Project Digital Twin canonical documents in order.
3. Read only the current work package section.
4. Inspect target files, direct dependencies, direct callers and related tests.
5. Implement and test one package.
6. Update this file with executed evidence.
7. Continue only after acceptance criteria pass.

## Latest completed package

```text
Completed work package: PDT-1 — Versioned contracts
PR/commit: branch pdt-1-versioned-contracts
Changed files:
- agent/project_twin/__init__.py (new) — public surface re-export
- agent/project_twin/types.py (new) — enums, literals, CONTRACT_VERSION
- agent/project_twin/versioning.py (new) — version constant + compatibility helpers
- agent/project_twin/events.py (new) — TwinEventEnvelope + EVENT_TYPES catalog
- agent/project_twin/contracts.py (new) — schemas + public ports (Protocols)
- tests/test_project_twin_contracts.py (new)
- tests/test_project_twin_baseline.py — flip the PDT-0 absence pin to PDT-1 presence
- docs/atlas_project_digital_twin_current_status.md (this file)
Behavior implemented:
- atlas.project_twin.v1 contracts: TwinNode/Edge/Evidence/RuntimeObservation/Revision/Delta,
  query/trace/impact/context schemas, store result envelopes, and seven public ports.
- Deterministic pydantic-v2 serialization; invalid confidence/status/domain rejected;
  query/depth/budget bounds enforced; version compatibility helpers; event envelope.
- No storage/network/framework dependency in the contract package (enforced by test).
Focused tests:
- python -m pytest -q tests/test_project_twin_contracts.py -> 23 passed.
Syntax/type checks:
- python -m py_compile agent/project_twin/*.py -> passed.
Affected tests:
- python -m pytest -q tests/test_project_twin_baseline.py tests/test_project_twin_contracts.py
  -> 44 passed.
Safety invariants:
- Contract-level: SkillActivation carries no authority fields; RuntimeObservation supports
  truthful "unavailable"; contracts cannot mutate workflow/PlanPool (no store/exec deps).
Known limitations:
- Contracts only; no store, projection or consumer wiring yet (PDT-2+).
Remaining blockers: None.
Next work package: PDT-2 — Local transactional Twin Store.
```

## Earlier completed package

```text
Completed work package: PDT-0 — Baseline and boundary inventory
PR/commit: branch pdt-0-baseline-inventory
Changed files:
- docs/atlas_project_digital_twin_baseline_inventory.md (new)
- tests/test_project_twin_baseline.py (new)
- docs/atlas_project_digital_twin_current_status.md (this file)
Behavior implemented:
- Read-only baseline inventory of all PDT-dependent capabilities with authoritative
  owners, duplication, reusable contracts, migration risk and PDT destinations.
- Regression fixtures pinning reused-owner importability, deterministic CodeIntel
  symbol/dependency output, HybridMemoryStore short/long-term behavior, and absence
  of any project_twin package at baseline.
Focused tests:
- python -m pytest -q tests/test_project_twin_baseline.py -> 21 passed.
Syntax/type checks:
- python -m pytest collected/imported all 16 reused owner modules successfully.
Affected tests:
- No production code changed; PDT-0 adds only a doc and a new test module.
Safety invariants:
- No workflow state, PlanPool authority, approval, allowed-path, Safe Apply, rollback,
  retry, command allowlist, remote-push/merge or verification behavior touched.
Known limitations:
- Inventory is descriptive; no twin contracts/store exist yet (PDT-1/PDT-2).
- Skill registry and graph visualization are confirmed gaps (PDT-7 / PDT-13).
Remaining blockers: None.
Next work package: PDT-1 — Versioned contracts.
```

## Update template

```text
Completed work package:
PR/commit:
Changed files:
Behavior implemented:
Focused tests:
Syntax/type checks:
Affected tests:
Safety invariants:
Known limitations:
Remaining blockers:
Next work package:
```
