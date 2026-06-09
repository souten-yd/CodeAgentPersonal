# Atlas Project Intelligence — Architecture

Status: canonical architecture.

## 1. Architectural objective

The system must deliver complete Project Intelligence while remaining maintainable, replaceable, and portable. Isolation is performed at module boundaries. Internal functions and classes are implementation details unless explicitly exported by a module facade.

The four primary modules are:

```text
Digital Twin Module
Architecture Blueprint Module
Convergence Module
Project Intelligence Module
```

Atlas-specific planning, generation, verification, API, and UI integrations live outside these portable modules.

## 2. System context

```text
Requirements / Conversation / PlanPool / Safe Apply / Verification / Nexus / Memory
                                  |
                                  v
                    Atlas Integration Adapters
                                  |
                                  v
                    Project Intelligence Module
                     /            |             \
                    v             v              v
          Digital Twin       Blueprint      Convergence
                    \             |             /
                     \            |            /
                      +------ Context Packages
                                  |
                                  v
                  Planner / Generator / Verifier / Repair
```

## 3. Dependency direction

Allowed:

```text
Atlas consumers
  -> Atlas integration adapters
  -> Project Intelligence facade
  -> Digital Twin / Blueprint / Convergence facades
  -> module-internal services and persistence adapters
```

Forbidden:

```text
Digital Twin core -> AtlasPlanPoolStorage
Blueprint core -> Digital Twin private store
Convergence core -> SQLite private tables
Planner -> Digital Twin SQLite store
Generator -> Blueprint private models
UI -> module-internal evaluator
Portable core -> FastAPI, ui.html, web/js, app/api
```

The Convergence Module may consume public Blueprint and Digital Twin snapshots or packages. Digital Twin and Blueprint do not depend on each other.

## 4. Recommended package layout

The implementation may adapt this layout to current repository conventions, but the dependency boundaries are mandatory.

```text
agent/project_intelligence/
  facade.py
  contracts.py
  models.py
  coordinator.py
  rollout.py
  telemetry.py
  adapters/
    atlas_events.py
    atlas_planning.py
    atlas_generation.py
    atlas_verification.py

agent/project_twin/
  facade.py
  contracts.py
  coordinator.py
  lifecycle.py
  store.py
  graph/
  analyzers/
  runtime/
  context/
  compatibility/

agent/architecture_blueprint/
  facade.py
  contracts.py
  models.py
  store.py
  generator.py
  reviewer.py
  validator.py
  mapping.py

agent/project_convergence/
  facade.py
  contracts.py
  models.py
  store.py
  matcher.py
  evaluator.py
  policy.py
```

Existing `agent/project_twin/` code is evolved behind the new facade rather than copied into a competing graph system.

## 5. Module facades

### 5.1 Digital Twin Module

External responsibilities:

- open and identify a project/workspace;
- build, refresh, rebuild, and report readiness;
- ingest canonical project events;
- ingest runtime observations;
- query structure, behavior, delivery trace, path, impact, and tests;
- create phase-aware context packages;
- expose immutable revision identifiers and diagnostics.

Internal responsibilities:

- source snapshots and change detection;
- graph identity and persistence;
- structural, semantic, call, control-flow, data-flow, state/event, side-effect, API/DB/config/UI, and runtime analysis;
- static/runtime reconciliation;
- incremental invalidation;
- source materialization;
- context ranking and token budgeting.

### 5.2 Architecture Blueprint Module

External responsibilities:

- create, review, activate, revise, supersede, and read Blueprint revisions;
- validate exact file manifests, interfaces, dependencies, behavior, startup, and verification contracts;
- preserve architecture decision provenance and authority.

It never marks code implemented or verified.

### 5.3 Convergence Module

External responsibilities:

- compare one Blueprint revision against one Actual Twin revision;
- map Blueprint elements to actual references;
- evaluate structural, interface, behavioral, data, configuration, verification, nonfunctional, and delivery-trace dimensions;
- return gaps and a bounded next-action decision;
- preserve report history.

It never mutates the workspace, PlanPool, or Blueprint.

### 5.4 Project Intelligence Module

External responsibilities:

- prepare a project for Atlas;
- prepare planning and generation context packages;
- record Safe Apply and verification outcomes;
- trigger refresh and convergence evaluation;
- expose progress and rollout diagnostics;
- coordinate modules without assuming their private storage.

It is the preferred Atlas integration surface.

## 6. Actual versus planned namespaces

Actual references use existing or extended namespaces:

```text
file://
dir://
module://
py://
js://
route://
schema://
dbtable://
state://
event://
side_effect://
test://
observation://
evidence://
```

Blueprint references are separate:

```text
bp-component://
bp-file://
bp-symbol://
bp-api://
bp-schema://
bp-data://
bp-behavior://
bp-state://
bp-test://
bp-runtime://
```

A planned file must never be represented as `file://` before it exists in the source snapshot.

## 7. Digital Twin graph architecture

The Digital Twin uses a common revisioned graph model while separating analysis capabilities internally.

### 7.1 Structural graph

Nodes include repository, directory, file, package, module, class, function, method, variable, constant, type, configuration, dependency, test, and fixture.

Edges include contains, defines, imports, exports, references, and depends_on.

### 7.2 Semantic and call graph

The analyzer resolves definitions, references, aliases, re-exports, inheritance, overrides, Protocol/interface implementation, decorators, dependency injection, and call targets.

Call sites may produce `may_call` edges when dynamic dispatch is unresolved. Only deterministic resolution or runtime evidence produces stronger relations.

### 7.3 Control-flow graph

Each callable may contain entry, basic block, branch, loop, exception handler, return, and exit nodes. Edges include next, true_branch, false_branch, loop_back, raises, handles, and returns.

### 7.4 Data-flow graph

Data is traced through parameters, assignments, fields, transformations, returns, and external sinks. Initial delivery is intraprocedural, followed by interprocedural parameter/return propagation and API-to-persistence paths.

### 7.5 State, event, and recovery graph

State nodes and transition edges capture workflow state, UI state, jobs, sessions, entities, retries, timeout, rollback, and recovery. Events identify producers, consumers, handlers, scheduling, and causation.

### 7.6 Resource and side-effect graph

Side effects identify concrete targets when possible:

- DB table/query/transaction;
- file path and operation;
- network method/host/route;
- process command and arguments;
- UI target and rendering action.

### 7.7 API, schema, persistence, configuration, and dependency graph

The graph links route -> handler -> service -> repository -> query -> table -> response schema, and also includes environment variables, package manifests, Docker/build/start commands, migrations, and configuration consumers.

### 7.8 UI and rendering graph

For HTML/JS/TS/Vue, the graph links control -> event -> handler -> state mutation -> API call -> response -> render. Vue components, props, emits, reactive state, computed values, watchers, routes, DOM selectors, Canvas rendering, and assets are supported incrementally.

### 7.9 Runtime graph

Runtime observations include tests, coverage, stack frames, API request/response, browser network and console, DB/file/process observations, UI interactions, latency, and memory. Runtime edges remain distinct from static inference.

### 7.10 Delivery and evidence graph

Canonical Atlas events project:

```text
Conversation -> Message -> Requirement -> Blueprint Element -> PlanItem
-> Proposal -> Run -> File/Symbol -> Test -> Verification -> Evidence
```

Canonical stores remain authoritative.

## 8. Analysis adapter model

Language and framework analyzers are internal Digital Twin adapters with one coarse contract:

```python
class LanguageAnalysisAdapter(Protocol):
    def describe(self) -> AnalyzerDescriptor: ...
    def analyze(self, request: LanguageAnalysisRequest) -> LanguageAnalysisResult: ...
```

One result may contain all supported graph facts and diagnostics. Capability declarations identify which facts are available. The external Digital Twin facade does not expose one port per graph micro-feature.

Required initial adapters:

- Python AST and semantic/LSP adapter;
- JavaScript/TypeScript/Vue adapter;
- FastAPI/Pydantic adapter;
- SQL/SQLite/SQLAlchemy adapter;
- package/configuration adapter;
- pytest runtime adapter;
- Playwright/browser runtime adapter;
- API/Atlas Play runtime adapter.

## 9. Lifecycle

### Project preparation

```text
resolve project/workspace identity
-> read health and parser versions
-> compare source revision
-> full build or incremental refresh
-> return readiness
```

Readiness states:

```text
absent, building, ready, stale, degraded, corrupt, disabled
```

### Safe Apply boundary

```text
Safe Apply succeeds
-> canonical result committed
-> event/outbox record
-> Twin incremental refresh for actual changed files
-> affected facts invalidated and rebuilt
-> Convergence reevaluated
```

Twin projection failure must not rewrite the canonical Safe Apply result. It marks the Twin degraded and records a retryable projection job.

### Verification boundary

```text
canonical verification result
-> runtime normalization
-> Twin observation ingestion
-> static/runtime reconciliation
-> evidence links
-> Convergence reevaluation
```

## 10. Blueprint architecture

A Blueprint revision contains:

- scope: full_project, change_set, or repair;
- source requirement IDs;
- architecture decisions and authority;
- exact planned elements and relations;
- file manifest and dependency order;
- interface, schema, behavior, startup, runtime, and verification contracts;
- assumptions, constraints, unresolved decisions;
- source Actual Twin revision;
- immutable parent revision linkage.

Lifecycle:

```text
proposed -> reviewed -> approved -> active -> materializing
-> satisfied or diverged -> superseded
```

Only one active revision exists per project/scope policy.

## 11. Convergence architecture

Element matching order:

1. explicit expected actual reference;
2. exact canonical identity;
3. path and symbol signature;
4. API method/path;
5. schema/data identity;
6. structural relation;
7. heuristic candidate, never silently accepted as verified.

Element states:

```text
absent, partial, materialized, observed, verified, divergent, blocked, stale
```

Decision actions:

```text
continue
complete
repair_current_item
replan_downstream
revise_blueprint
request_critical_decision
halt_unsafe
```

Completion requires zero mandatory gaps, zero unresolved critical decisions, zero failed required verification, no stale mandatory evidence, and full mandatory requirement coverage.

## 12. Planner and execution integration

Planner receives a single `PlanningContextPackage`. Generator receives a single `GenerationContextPackage`. They do not query graph or Blueprint stores directly.

PlanPool remains authoritative and gains references to:

- Blueprint revision;
- Actual Twin revision;
- Convergence report;
- context manifest;
- planning envelope hash.

Each PlanItem may reference Blueprint elements, expected actual refs, convergence criteria, interface contracts, behavior contracts, and required evidence.

## 13. Existing feature reorganization

Existing services are migrated using four classifications:

- KEEP: canonical authority remains;
- ADAPT: used behind a new module facade;
- REPLACE: superseded after measured parity;
- REMOVE: deleted only after consumer count reaches zero and rollback evidence exists.

Migration order:

```text
inventory and consumer map
-> facade and compatibility adapters
-> shadow comparison
-> read-only consumer cutover
-> planning cutover
-> generation cutover
-> verification/repair cutover
-> final-rollup cutover
-> legacy retirement
```

## 14. Rollout

Modes:

```text
off
shadow
planning_active
generation_active
verification_active
repair_active
greenfield_supervised
full_active
```

The old Project Twin environment variables remain as compatibility inputs until final retirement.

## 15. Nonfunctional requirements

- deterministic identities and idempotent event ingestion;
- project and workspace isolation;
- atomic revisions and migration rollback;
- incremental refresh and convergence;
- bounded graph traversal and token usage;
- no silent fallback from unavailable to passed;
- restart-safe jobs and checkpoints;
- Windows, Linux, Docker, and Runpod compatibility;
- architecture-boundary tests preventing forbidden imports;
- ability to instantiate the portable modules without Atlas.
