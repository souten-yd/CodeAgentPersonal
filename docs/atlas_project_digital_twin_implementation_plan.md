# Atlas Project Digital Twin Implementation Plan

## Execution model

Implement `PDT-0` through `PDT-14` sequentially.

Rules:

- one work package at a time;
- small reviewable PRs;
- no broad rewrite;
- public contracts before consumers;
- focused tests, syntax/type checks, affected tests;
- update current status after every package;
- do not weaken Atlas safety or truthful verification;
- do not report unexecuted tests as passed.

## PDT-0 — Baseline and boundary inventory

### Goal

Establish current implementation facts before production changes.

### Inspect

- Repo Index and CodeIntel
- ContextBuilder
- project investigation services
- static graph or symbol services
- requirement tracing
- PlanPool/proposal/verification stores
- runtime trace/browser observations
- `HybridMemoryStore`
- current Skill loader/registry
- Nexus evidence stores
- conversation/session implementations

### Deliverables

- baseline inventory document;
- authoritative ownership map;
- duplicate/legacy path list;
- migration constraints;
- regression fixtures;
- initial benchmark scenarios.

### Acceptance

- current behavior is covered by tests;
- no production path is replaced;
- next work package target files are explicit.

## PDT-1 — Versioned contracts

### Goal

Add the v1 contract package and public ports.

### Deliverables

```text
agent/project_twin/contracts.py
agent/project_twin/types.py
agent/project_twin/events.py
agent/project_twin/versioning.py
tests/test_project_twin_contracts.py
```

### Acceptance

- schemas serialize deterministically;
- invalid values fail;
- no storage dependency in contract package;
- public ports are importable and documented.

## PDT-2 — Local transactional Twin Store

### Goal

Implement SQLite storage behind `ProjectTwinPort`.

### Deliverables

- migrations;
- repository;
- transaction boundary;
- revision/snapshot services;
- health diagnostics;
- project isolation;
- idempotency;
- stale revision protection.

### Acceptance

- delta is atomic;
- failure leaves no partial revision;
- repeated idempotency key is stable;
- project data cannot cross scope;
- migration rollback is tested.

## PDT-3 — Static Structural Graph

### Goal

Build initial deterministic structure for Python and current web assets.

### Deliverables

- repository/file/module/package nodes;
- Python class/function/method/type nodes;
- imports/inheritance/basic calls;
- FastAPI route projection;
- test/fixture nodes;
- HTML script/style links;
- basic JS import/event-handler links;
- incremental file refresh.

### Acceptance

- canonical refs are deterministic;
- single-file update avoids unrelated rebuild;
- parse failures create diagnostics;
- deleted symbols are invalidated, not silently lost.

## PDT-4 — Intent and Delivery Trace

### Goal

Connect intent to verified implementation.

### Deliverables

- Conversation/Message references;
- Requirement and Constraint projection;
- PlanPool/PlanItem projection;
- Proposal/Run/Apply projection;
- File/Symbol change links;
- Test/Verification/Evidence links;
- missing-trace diagnostics.

### Acceptance

For a real Atlas task:

```text
Message -> Requirement -> PlanItem -> File/Symbol -> Test -> Evidence
```

is queryable with source IDs.

## PDT-5 — Minimal Context Broker

### Goal

Use the twin in at least Planner and patch generation without replacing all context paths.

### Deliverables

- request/slice services;
- ranking and token budget;
- freshness/confidence filtering;
- inclusion/exclusion reasons;
- planner pilot adapter;
- patch-generation pilot adapter.

### Acceptance

- context remains within budget;
- required safety/requirements are not dropped;
- private store is not accessed by consumers;
- disabled broker preserves current behavior.

## PDT-6 — Memory integration

### Goal

Integrate existing Memory without creating a competing memory subsystem.

### Deliverables

- `HybridMemoryStore` adapter;
- project-scoped recall;
- verified promotion policy;
- evidence links;
- supersede/invalidate;
- ArchitectureDecision/TaskOutcome/ModuleMap/Risk/Incident relations.

### Acceptance

- unverified inference is not durable;
- verified outcome can be promoted;
- superseded memory is excluded from normal recall but remains historical;
- project isolation holds.

## PDT-7 — Skill integration

### Goal

Integrate existing `SKILL.md` assets into Atlas and the twin.

### Deliverables

- Skill Registry;
- resolver;
- version/content hash;
- applicability metadata;
- activation reason;
- outcome/effectiveness;
- Context Broker skill items;
- safety precedence tests.

### Acceptance

- task-relevant skills are selected with reasons;
- exact version is recorded;
- skills cannot expand allowed paths, commands or approval authority.

## PDT-8 — Behavioral Graph

### Goal

Represent inferred project behavior.

### Deliverables

- event/action/state/transition schemas;
- data-flow and side-effect relations;
- API/service/DB/file/network/UI inference;
- explicit confidence;
- uncertainty diagnostics.

### Acceptance

- at least one Atlas UI path is modeled;
- side effects are queryable;
- heuristic facts are never marked verified.

## PDT-9 — Runtime collectors

### Goal

Add safe runtime evidence.

### Deliverables

- pytest collector;
- Playwright/browser collector;
- API observation collector;
- Atlas Play console/failed-request adapter;
- observation normalizer;
- collector availability diagnostics.

### Acceptance

- pass/fail/unavailable are distinct;
- evidence links to tests/symbols/paths where possible;
- unavailable instrumentation never fabricates success.

## PDT-10 — Static/runtime reconciliation

### Goal

Combine inference and observation truthfully.

### Deliverables

- contradiction detection;
- invalidation;
- confidence update;
- stale evidence policy;
- repeated observation support;
- reconciliation diagnostics.

### Acceptance

- contradictory observations preserve history;
- context identifies contradiction;
- verified observation outranks stale inference without deleting audit history.

## PDT-11 — Impact and path analysis

### Goal

Provide explainable impact and flow queries.

### Deliverables

- structural impact;
- transitive call/reference impact;
- behavior/state impact;
- requirement impact;
- side-effect impact;
- recommended tests;
- historical risk;
- path explanation.

### Acceptance

Automated scenarios answer:

- function change impact;
- UI-to-persistence path;
- API side effects;
- recommended tests.

## PDT-12 — Nexus integration

### Goal

Connect external evidence.

### Deliverables

- Document/Evidence/Report references;
- support/contradict edges;
- architecture decision evidence;
- retrieval date/content hash;
- Context Broker Nexus section.

### Acceptance

- external evidence retains source;
- contradictions remain explicit;
- Nexus claims do not become verified code truth automatically.

## PDT-13 — Project Twin API and UI

### Goal

Expose useful inspection without workflow authority.

### Deliverables

- health/revision/node/query/path/impact/context APIs;
- Project Twin panel;
- Structure/Behavior/Delivery/History/Impact views;
- lazy expansion;
- source navigation;
- confidence/status/revision filters.

### Acceptance

- initial graph is bounded;
- large projects paginate;
- UI cannot authorize execution;
- mobile layout remains usable.

## PDT-14 — E2E benchmark and rollout

### Goal

Prove the twin improves Atlas.

### Benchmark scenarios

1. function impact;
2. UI-to-persistence trace;
3. requirement implementation trace;
4. API side-effect trace;
5. static/runtime contradiction;
6. test recommendation;
7. design decision history;
8. incident/root-cause/repair history;
9. project isolation;
10. token-bounded context;
11. incremental refresh;
12. Memory promotion;
13. Skill activation/safety;
14. Nexus evidence linkage.

### Rollout

- disabled-by-default feature flag first;
- shadow comparison with current context;
- collect quality/latency/token metrics;
- promote per phase after acceptance;
- retain rollback path;
- remove duplicate legacy paths only after parity.

## Cross-package invariants

Every package preserves:

- backend workflow and PlanPool authority;
- approval and critical-event behavior;
- allowed paths;
- rollback;
- retry limits;
- no direct merge/remote push/self-apply;
- truthful test and runtime reporting;
- project isolation;
- versioned interfaces;
- no private store dependency from agents/UI.

## Final acceptance

PDT is complete only when all mandatory packages are completed and current status contains executed evidence for the final benchmark.
