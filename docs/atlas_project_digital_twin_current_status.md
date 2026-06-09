# Atlas Project Digital Twin Current Status

> Mutable checkpoint for Codex/Claude goal execution.  
> Update after every work package.  
> Do not infer completion from planning documents.

## Goal status

- Overall: PDT-4 completed
- Canonical goal: `docs/atlas_project_digital_twin_goal.md`
- Architecture: `docs/atlas_project_digital_twin_architecture.md`
- Contracts: `docs/atlas_project_digital_twin_contracts.md`
- Implementation plan: `docs/atlas_project_digital_twin_implementation_plan.md`
- Agent entrypoint: `docs/atlas_project_digital_twin_agent_entrypoint.md`
- Current work package: `PDT-5`
- Next action: Minimal Context Broker (phase-aware bounded slice; planner/patch pilot adapters)
- Blocker: None recorded
- Safety posture: Existing Atlas authority and verification rules unchanged

## Work package table

| WP | Title | Status | PR/Commit | Executed evidence |
|---|---|---|---|---|
| PDT-0 | Baseline and boundary inventory | Completed | pdt-0-baseline-inventory | `pytest -q tests/test_project_twin_baseline.py` -> 21 passed |
| PDT-1 | Versioned contracts | Completed | pdt-1-versioned-contracts | `pytest -q tests/test_project_twin_contracts.py` -> 23 passed; baseline -> 21 passed |
| PDT-2 | Local transactional Twin Store | Completed | pdt-2-twin-store | `pytest -q tests/test_project_twin_store.py` -> 13 passed |
| PDT-3 | Static Structural Graph | Completed | pdt-3-static-graph | `pytest -q tests/test_project_twin_static_graph.py` -> 8 passed |
| PDT-4 | Intent and Delivery Trace | Completed | pdt-4-intent-delivery-trace | `pytest -q tests/test_project_twin_intent_trace.py` -> 5 passed |
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
Completed work package: PDT-4 — Intent and Delivery Trace
PR/commit: branch pdt-4-intent-delivery-trace
Changed files:
- agent/project_twin/intent_trace.py (new) — IntentTracePort projector
- tests/test_project_twin_intent_trace.py (new)
- docs/atlas_project_digital_twin_current_status.md (this file)
Behavior implemented:
- Projects Conversation/Message, Requirement/Constraint, Plan/PlanItem, Proposal/Run,
  Verification and Evidence references (IDs) plus their relationships into the
  intent_delivery domain as a reference/relation model (canonical systems stay
  authoritative; derivation=canonical_projection).
- Cross-domain edges link PlanItems to structural file:///py:// nodes and to PDT-3
  test:// nodes by shared canonical ref / hashed node id.
- Missing links (no source message, no requirement, no plan item) emit diagnostics
  instead of fabricated edges; unsupported events are reported.
- End-to-end Message -> Requirement -> PlanItem -> File/Symbol and PlanItem ->
  Verification -> Test -> Evidence is queryable with source IDs.
Focused tests:
- python -m pytest -q tests/test_project_twin_intent_trace.py -> 5 passed.
Syntax/type checks:
- python -m py_compile agent/project_twin/intent_trace.py -> passed.
Affected tests:
- python -m pytest -q tests/test_project_twin_intent_trace.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_store.py tests/test_project_twin_contracts.py tests/test_project_twin_baseline.py
  -> 70 passed.
Safety invariants:
- Read-only projection of references; no PlanPool/workflow mutation; the twin does not
  replace conversation/PlanPool/verification authority.
Known limitations:
- Projector consumes structured event payloads; wiring real Atlas event producers is a
  later integration step. trace_path uses undirected reachability until PDT-11.
Remaining blockers: None.
Next work package: PDT-5 — Minimal Context Broker.
```

## Earlier completed package

```text
Completed work package: PDT-3 — Static Structural Graph
PR/commit: branch pdt-3-static-graph
Changed files:
- agent/project_twin/static_graph.py (new) — pure StaticAnalysisPort implementation
- agent/project_twin/projection.py (new) — StaticProjectionService (analyzer -> store)
- tests/test_project_twin_static_graph.py (new)
- docs/atlas_project_digital_twin_current_status.md (this file)
Behavior implemented:
- Deterministic projection of repository/dir/file/module nodes, Python class/function/
  method nodes, imports/inheritance/name-based call edges, FastAPI route projection,
  test + pytest-fixture nodes, HTML <script>/<link>/<style> asset links, and basic JS
  import + event-handler links. Node ids are a stable hash of the canonical ref.
- Parse/read failures emit diagnostics; the file node is still created.
- Incremental refresh: changed-file-only re-emission; unrelated nodes are not rebuilt;
  deleted symbols/edges are explicitly invalidated (not silently lost) and linked to head.
Focused tests:
- python -m pytest -q tests/test_project_twin_static_graph.py -> 8 passed.
Syntax/type checks:
- python -m py_compile agent/project_twin/static_graph.py agent/project_twin/projection.py -> passed.
Affected tests:
- python -m pytest -q tests/test_project_twin_static_graph.py tests/test_project_twin_store.py
  tests/test_project_twin_contracts.py tests/test_project_twin_baseline.py -> 65 passed.
Safety invariants:
- Projection is the parser->store path via typed delta; no workflow/PlanPool mutation.
- Heuristic JS/inline facts use heuristic_static derivation and lower confidence; never
  marked verified.
Known limitations:
- Call/inheritance targets are name-based (pyname:// refs), not yet resolved to defs.
- JS analysis is regex-based (heuristic). Full resolution is later behavioral/runtime work.
Remaining blockers: None.
Next work package: PDT-4 — Intent and Delivery Trace.
```

## Earlier completed package

```text
Completed work package: PDT-2 — Local transactional Twin Store
PR/commit: branch pdt-2-twin-store
Changed files:
- agent/project_twin/migrations.py (new) — SQLite schema + transactional migration runner
- agent/project_twin/store.py (new) — SqliteProjectTwinStore implementing ProjectTwinPort
- tests/test_project_twin_store.py (new)
- docs/atlas_project_digital_twin_current_status.md (this file)
Behavior implemented:
- One-transaction-per-delta apply with rollback on any failure (no partial revision).
- Idempotent delta application keyed by (project_id, idempotency_key) — repeat is stable.
- Stale-base-revision rejection; revision parent linkage; head pointer maintenance.
- Project isolation: payload scope check + project-scoped reads/writes.
- Supersede-by-canonical_ref with preserved history; explicit invalidation with counts.
- Current and point-in-time snapshots; filtered/paginated query; health diagnostics.
- Foreign keys ON, WAL on file DBs, autocommit connection with explicit BEGIN/COMMIT.
- trace_path/assess_impact return truthful "analysis_deferred" results (full in PDT-11).
Focused tests:
- python -m pytest -q tests/test_project_twin_store.py -> 13 passed.
Syntax/type checks:
- python -m py_compile agent/project_twin/migrations.py agent/project_twin/store.py -> passed.
Affected tests:
- python -m pytest -q tests/test_project_twin_store.py tests/test_project_twin_baseline.py
  tests/test_project_twin_contracts.py -> 57 passed.
Safety invariants:
- Store touches only its own SQLite tables; consumers depend on ProjectTwinPort.
- No workflow/PlanPool/approval/allowed-path/Safe Apply/verification behavior touched.
- Migration failure rolls back and is not recorded (tested).
Known limitations:
- query traversal is shallow (single hop); deep path/impact analysis is PDT-11.
- Store is not yet wired to any producer; PDT-3 adds the static projection.
Remaining blockers: None.
Next work package: PDT-3 — Static Structural Graph.
```

## Earlier completed package

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
