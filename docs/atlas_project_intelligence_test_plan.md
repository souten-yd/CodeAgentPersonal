# Atlas Project Intelligence — Test and Verification Plan

Status: canonical test plan.

## 1. Purpose

This plan defines the evidence required to implement and roll out Digital Twin Module, Architecture Blueprint Module, Convergence Module, Project Intelligence Module, Greenfield generation, and legacy consolidation without false completion or regression.

A test is evidence only when it was actually executed against the relevant revision. Unavailable tooling or environment is recorded as `unavailable`; it is never converted to success.

## 2. Test layers

Every work package uses the following layers as applicable:

1. contract and schema tests;
2. architecture-boundary tests;
3. module unit tests;
4. adapter conformance tests;
5. integration tests;
6. fault-injection and recovery tests;
7. real Atlas E2E tests;
8. cross-platform and scale tests;
9. comparative benchmark tests.

The required package sequence is:

```text
focused tests
-> syntax/type checks
-> directly affected tests
-> module acceptance scenario
-> milestone integration tests
```

## 3. Contract tests

### Common requirements

Test:

- deterministic serialization;
- version presence and compatibility;
- tolerant reading of additive fields;
- rejection of invalid required state;
- immutable revision semantics;
- project/workspace scope validation;
- typed errors rather than empty success;
- old `atlas.project_twin.v1` compatibility where specified.

### Digital Twin contracts

Test lifecycle requests/results, event envelopes, query types, context packages, runtime observations, readiness states, and context manifests.

### Blueprint contracts

Test immutable revisions, valid lifecycle states, element/ref namespaces, architecture decision authority, exact file manifest requirements, and child revision creation.

### Convergence contracts

Test element states, mismatch explanations, mandatory versus optional gaps, decision action enum, and report revision identities.

### Project Intelligence contracts

Test ProjectMode, PlanningContextPackage, GenerationContextPackage, apply/verification result packages, and legacy-default loading.

## 4. Architecture-boundary tests

Automated tests must reject forbidden imports and direct storage access.

Forbidden examples:

```text
project_twin core -> atlas_plan_pool_storage
architecture_blueprint core -> project_twin private store
project_convergence core -> sqlite private table
planner -> project_twin.store
generator -> architecture_blueprint.store
UI/API -> convergence.matcher or evaluator internals
portable modules -> FastAPI, web/js, ui.html
```

Allowed dependencies are checked against an explicit module-boundary map. New exceptions require architecture-document revision and a focused test.

Standalone import tests instantiate the portable modules without importing Atlas workflow, API, or UI packages.

## 5. Persistence tests

For every persistence adapter:

- atomic commit;
- rollback on injected failure;
- stale parent revision rejection;
- idempotency key behavior;
- point-in-time read;
- project/workspace isolation;
- migration repeatability;
- integrity check;
- corruption reporting;
- close/reopen persistence;
- restart recovery of pending jobs;
- no rewrite of canonical Atlas stores.

## 6. Digital Twin Module tests

### 6.1 Lifecycle and incremental refresh

Scenarios:

- nonexistent project path;
- empty directory;
- existing repository full build;
- single-file change;
- file deletion;
- rename;
- parser-version change;
- external workspace change;
- interrupted refresh and restart;
- simultaneous worktrees;
- corrupt store and rebuild.

Assertions:

- deterministic project/workspace identity;
- unrelated facts are not rebuilt unnecessarily;
- deleted facts become historical/invalidated;
- stale state is explicit;
- same change/event is idempotent.

### 6.2 Structural and semantic graph

Python fixtures must cover:

- same symbol name in different modules;
- relative and absolute imports;
- aliases and re-exports;
- class inheritance and override;
- Protocol/interface implementation;
- decorators;
- dependency injection patterns used in KasaneCore;
- direct, method, callback, and unresolved dynamic calls;
- tests and fixtures.

JavaScript/TypeScript/Vue fixtures must cover:

- imports/exports;
- components;
- props and emits;
- router and API client;
- event handlers;
- reactive state;
- asset references.

Metrics:

- symbol resolution precision;
- call target precision/recall;
- unresolved-call honesty;
- incremental invalidation correctness.

### 6.3 Behavioral graph

Fixtures must cover:

- branches and loops;
- returns and exceptions;
- try/except/finally;
- async and background boundaries;
- retry and timeout;
- rollback and recovery;
- parameter/assignment/return data flow;
- request -> schema -> service -> repository -> database;
- UI event -> state -> API -> response -> render;
- file/network/process/UI side effects;
- concrete resource identity where statically resolvable.

Assertions:

- inferred facts carry provenance/confidence;
- unsupported constructs create diagnostics;
- no inferred fact is marked verified;
- exception/recovery paths are reachable only through valid CFG edges;
- data does not flow across impossible branch paths in supported fixtures.

### 6.4 Runtime and reconciliation

Collectors:

- pytest result and coverage;
- Playwright/browser network and console;
- API verification;
- Atlas Play;
- optional DB/file/process observation.

Assertions:

- passed, failed, observed, unavailable remain distinct;
- coverage and stack frames map to source revision and symbol;
- old observations become stale after source change;
- confirmation upgrades only matching facts;
- contradiction preserves history;
- collector failure cannot satisfy a requirement.

### 6.5 Query/context/impact

Test:

- bounded path traversal;
- cycle handling;
- impact depth and domain filters;
- affected requirement discovery;
- side-effect and runtime path inclusion;
- test selection;
- token budget;
- mandatory requirement priority;
- source material revision matching;
- stale and contradiction penalties;
- excluded-item reasons;
- no whole-graph prompt dump.

Metrics:

- impact precision and recall;
- test-recommendation precision;
- context tokens;
- refresh and query latency.

## 7. Canonical event and delivery-trace tests

Use real canonical services where practical. Required scenarios:

```text
conversation message
-> requirement confirm/revise
-> plan create/revise
-> item start/complete/fail
-> proposal generate/approve/reject
-> Safe Apply
-> verification
-> evidence
```

Assertions:

- at-least-once replay is idempotent;
- correlation/run/pool/item IDs survive;
- failed and superseded history remains queryable;
- missing canonical links create diagnostics;
- Twin projection never mutates canonical workflow state;
- Safe Apply success is not rolled back by projection failure.

## 8. Blueprint Module tests

### 8.1 Lifecycle

Test:

- create proposed revision;
- review diagnostics;
- approve/activate;
- immutable activated revision;
- child revision;
- supersede;
- one active revision policy;
- rejection;
- project isolation.

### 8.2 Validation

Greenfield Blueprint must be rejected when missing:

- exact file manifest;
- entrypoint;
- dependency manifest when required;
- interface/schema contracts;
- startup/build/test command contracts;
- verification/runtime scenarios;
- requirement mapping.

Existing Change Blueprint must be rejected when it:

- redesigns unrelated scope without reason;
- omits preserve behavior;
- references nonexistent Actual facts as guaranteed;
- contains dependency cycles;
- requires an unresolved critical decision.

### 8.3 Decision authority

Test that model output can create `planner_recommendation` but cannot create `user_decision` without canonical user evidence.

## 9. Convergence Module tests

### 9.1 Matching

Test explicit refs, canonical refs, path/signature, API method/path, schema identity, structural relation, and heuristic candidates.

Heuristic-only matches remain uncertain until accepted by deterministic or runtime evidence.

### 9.2 Multidimensional evaluation

For each Blueprint element, test transitions:

```text
absent -> partial -> materialized -> observed -> verified
```

Also test divergent, blocked, and stale.

Required distinctions:

- file exists but interface missing;
- interface exists but behavior absent;
- static behavior inferred but runtime unobserved;
- runtime passed on old source revision;
- test exists but was not run;
- optional gap versus mandatory gap.

### 9.3 Decision policy

Cover every action:

- continue;
- complete;
- repair_current_item;
- replan_downstream;
- revise_blueprint;
- request_critical_decision;
- halt_unsafe.

Verify that local defects do not trigger whole Blueprint revision and that mandatory gaps prevent completion.

### 9.4 Incremental agreement

For affected elements, incremental reevaluation must equal a full reevaluation against the same revisions.

## 10. Planner and PlanPool tests

Test:

- PlanningContextPackage generation;
- Architecture, Delivery, and Repair planning phases;
- deterministic Blueprint dependency ordering;
- PlanItem Blueprint element IDs;
- exact target files/directories/operations;
- completed-item preservation;
- downstream-only replan;
- whole-pool replan only when required;
- old PlanPool compatibility defaults;
- context manifest persistence;
- off, shadow, and active behavior.

No test may assume that a Planner-generated target exists until Actual Twin confirms it.

## 11. Generator and repair tests

Test:

- current target content and base revision;
- stale Actual revision rejection/refresh;
- Blueprint interface and behavior contracts in generation input;
- missing-symbol honesty;
- multi-file name consistency;
- import/asset/API/schema/dependency consistency;
- prohibited divergence;
- context manifest on Proposal;
- local repair using actual verification evidence;
- bounded retry;
- escalation to downstream replan or Blueprint revision.

## 12. Verification and final-rollup tests

Test:

- verification recommendation from impact and Blueprint contract;
- result normalization to runtime observation;
- reconciliation;
- post-verification convergence;
- requirement-to-evidence trace;
- unavailable tool behavior;
- false-success cases;
- stale evidence;
- preserve-behavior regression;
- final completion gate.

A completion test must fail if any mandatory requirement lacks current evidence.

## 13. Greenfield real E2E tests

Tests begin from normal Atlas project/run entrypoints and an empty temporary directory. They must not construct Twin or Blueprint records directly in the test.

Required scenarios:

1. single HTML page;
2. HTML/JS/CSS app;
3. Python CLI;
4. FastAPI API;
5. FastAPI plus SQLite persistence;
6. Vue plus FastAPI integration;
7. restart during generation;
8. one intermediate PlanItem generation failure;
9. unresolved import repair;
10. missing dependency repair;
11. frontend/backend API mismatch repair;
12. invalid test-contract repair;
13. Blueprint revision only when target design is invalid;
14. final requirement/evidence coverage.

For UI scenarios, use Playwright where available and record unavailable otherwise.

## 14. Fault injection

Inject failures into:

- SQLite transaction;
- migration;
- source read;
- parser/analyzer;
- LSP availability;
- event replay;
- projection job interruption;
- context materialization;
- Planner response;
- Proposal generation;
- Safe Apply revision conflict;
- test runner;
- browser startup;
- runtime collector;
- process restart.

Assert no partial authoritative mutation and correct retry/degraded/block behavior.

## 15. Cross-platform matrix

Target environments:

| Environment | Required evidence |
|---|---|
| Windows | contracts, storage, lifecycle, Planner/Generator integration, representative Greenfield |
| Linux | same core suite plus runtime integrations |
| Docker | startup, paths, persistence, restart |
| Runpod | Linux/container behavior, remote paths, runtime availability |

Environment-specific unavailable features are listed in status with reason.

## 16. Scale and performance

Measure at minimum:

- initial build time;
- incremental refresh time;
- graph node/edge counts;
- query latency;
- context build latency and tokens;
- convergence full/incremental latency;
- storage size and compaction;
- memory use;
- event backlog recovery.

Baseline is captured in PI-0. Regression budgets are established before active rollout. A default 20% regression threshold may be used until a workload-specific threshold is justified.

## 17. Shadow and comparative benchmark

Compare:

```text
legacy context
Digital Twin context only
Digital Twin + Blueprint + Convergence
```

Then compare current Atlas and final Atlas under identical model, task, tools, token/retry budget, and environment.

Metrics:

- verified autonomous completion;
- false-success rate;
- autonomous recovery;
- regression escape;
- requirement coverage;
- convergence;
- impact precision/recall;
- test recommendation precision;
- context tokens;
- latency;
- human intervention;
- resume fidelity;
- cross-platform success;
- cost per verified task.

## 18. Legacy-retirement test gate

A legacy implementation can be removed only when:

- all known consumers use new facade or an approved compatibility adapter;
- shadow comparison passes or superiority is documented;
- focused, affected, module, and real E2E tests pass;
- rollback/recovery path is tested;
- no canonical data is lost;
- architecture-boundary tests reject reintroduction;
- migration matrix is updated.

## 19. Evidence recording format

Every completed work package records:

```text
command
working directory/environment
result count and status
test revision
unavailable checks
known limitations
```

Do not write `all tests pass` without the actual command and result.
