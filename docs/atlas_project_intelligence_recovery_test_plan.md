# Atlas Project Intelligence Recovery — Test and Evidence Plan

Status: canonical verification plan for PIR-0..PIR-15.

## 1. Evidence rules

1. Contracts, components, production wiring, and live execution are separate proof levels.
2. Mock or injected-runner tests prove component behavior only.
3. Production integration must invoke the real Atlas API/service path.
4. Build/start/runtime claims require real commands and observable readiness.
5. Restart claims require closing and reopening stores or processes.
6. Platform claims require runs on that platform.
7. Benchmark metrics must be computed from executed run artifacts.
8. `unavailable` never satisfies required evidence.
9. Every artifact records relevant source, Twin, Blueprint, PlanPool, Proposal, apply, verification, and Convergence revisions.

## 2. Test layers

| Layer | Required proof |
|---|---|
| Contract | facade/DTO/version compatibility |
| Unit | deterministic helper behavior |
| Module integration | concrete facade plus durable store |
| Atlas integration | real production caller invokes capability |
| Restart/fault | state survives reopen and failures are truthful |
| Fixture E2E | real temporary workspace and real commands |
| Live-model E2E | configured model through normal Atlas path |
| Platform | actual Windows/Linux/Docker/Runpod evidence |
| Benchmark | real legacy and final runs under identical constraints |

## 3. Mandatory common suites

### Contract and boundaries

Verify:

- all concrete modules satisfy public protocols;
- disabled facades remain fail-closed;
- portable modules do not import FastAPI, UI, app API, PlanPool storage, or private Atlas services;
- consumers never query private module tables;
- planned and Actual namespaces remain distinct.

### Persistence and restart

For every durable store:

1. create state;
2. close;
3. reopen the same path;
4. verify history, active pointers, idempotency, and isolation;
5. test migration and a corrupt copy;
6. retain the prior valid revision when activation fails.

Covers Twin graphs/observations/manifests, event projection, Blueprint lifecycle, Convergence reports/decisions, checkpoints, Greenfield sessions, rollout, telemetry, consumer inventory, and benchmark artifacts.

### Workspace isolation

Use the same project and artifact IDs with two workspace IDs. Verify no graph, event, Blueprint, Convergence, context, checkpoint, session, or telemetry leakage.

### Truthful verification

Verify:

- stale evidence cannot verify current source;
- unavailable cannot pass;
- observed is not verified;
- file existence is not behavior proof;
- no final completion while any mandatory evidence policy is unsatisfied;
- projection failure cannot undo canonical success.

## 4. PIR acceptance matrix

### PIR-0

- generated consumer inventory finds real production callers;
- all critical audit defects have regression tests or executable inspection checks;
- generated inventory artifact is committed or retained by CI;
- Foundation Track status is no longer treated as program completion.

### PIR-1

- concrete and disabled facade conformance;
- close/reopen durability;
- Blueprint approval/activation survives restart;
- Twin revision and Convergence report reload;
- workspace isolation;
- production constructors reject in-memory persistence.

### PIR-2

- app startup builds one concrete service;
- shutdown closes resources;
- off equals legacy behavior;
- shadow does not alter canonical input;
- active with disabled/corrupt modules fails preflight;
- rollout state survives restart;
- health API exposes no sensitive rows or secrets.

### PIR-3

Real fixture repositories cover Python modules, JS/TS/Vue, dirty worktree, rename/delete, parse failure, and path escape.

Verify full build, incremental refresh, dirty-tree revision, retired facts, prior revision retention, restart job recovery, and full-versus-incremental equivalence.

### PIR-4

- canonical operations emit after successful writes;
- durable event payload survives restart;
- duplicate replay is idempotent;
- project/workspace isolation;
- poison event is diagnosable without blocking later work;
- projection failure queues retry without rolling back Safe Apply;
- requirement-to-verification delivery path is queryable.

### PIR-5

- real verification artifact normalization;
- per-test coverage mapping;
- source/Twin revision separation;
- stale/fresh reconciliation;
- objective/phase-aware bounded context;
- symbol-range excerpts;
- labeled impact and test-selection precision/recall.

### PIR-6

Labeled corpus covers cross-module imports, alias/re-export, cycles, inheritance/override, Protocol/ABC, receiver types, candidate dispatch, FastAPI route/schema, TS exports, and Vue props/emits/handlers.

Record resolved-edge precision/recall, false-resolved edges, candidate coverage, incremental/full equivalence, latency, and graph size.

### PIR-7

Labeled corpus covers branch/loop/exception/finally, async, parameter-to-resource flow, cross-function returns, state transitions, retry/timeout/rollback, FastAPI request-to-DB, and Vue handler-to-API.

Verify real basic blocks, def-use paths, bounded interprocedural flow, correct handler scope, resource identities, and graceful budget degradation.

### PIR-8

- existing-project Change Blueprint;
- Greenfield full Blueprint;
- durable review/approval/activation;
- exact file/interface/API/schema/data/config/runtime/NFR contracts;
- command validation;
- unresolved decisions block activation through existing gates;
- full redesign of an existing project requires explicit approval.

### PIR-9

Typed fixtures cover missing materialization, signature/API/schema/data/config/dependency/behavior/state/resource mismatch, stale/unavailable evidence, delivery gaps, NFR gaps, rename/move, and ambiguity.

Verify immutable reproducible reports, correct revision identities, mandatory evidence policy, incremental/full equivalence, explicit element-to-PlanItem mapping, and no premature completion.

### PIR-10

Tests call the real plan-pool handler/service.

Verify off equivalence, shadow non-interference, non-empty active context, persisted revision metadata, stale refresh/blocking, cycle rejection, authoritative PlanPool creation, and completed-item preservation.

### PIR-11

Tests use real Proposal and Safe Apply services in a temporary workspace.

Verify generation package contents, pre-model revision validation, stale no-call behavior, Proposal metadata, post-apply Twin child revision, Convergence report, idempotent replay, retry after projection failure, and path safety.

### PIR-12

Tests use real verification, continuation, replanning, self-correction, critical-decision, and recovery services.

Scenarios: pass/continue, local repair, downstream replan, Blueprint revision, critical decision, unsafe halt, completion candidate, restart resume, external edit, and duplicate replay.

### PIR-13

Every scenario creates a real temporary workspace, enters through normal Atlas, uses authoritative PlanPool/Proposal/Safe Apply/Verification, executes real allowlisted commands, probes readiness, records evidence, and closes/reopens for restart.

Required scenarios:

1. Single HTML with browser assertion.
2. HTML + JS + CSS.
3. Python CLI with failing-test repair.
4. FastAPI API.
5. FastAPI + SQLite persistence/restart.
6. Frontend + backend browser-to-API flow.

A deterministic model stub may prove orchestration, but commands and workspace must be real. At least one live configured-model run is required for final completion.

### PIR-14

CI matrix records Linux, Windows, Docker, fixture E2E, restart/fault, and large-repository results; Runpod evidence is recorded when available.

Verify real consumer call counts, shadow parity, import lint, rollback drills, concurrency, bounded storage/context growth, compaction/export/import/corruption recovery, telemetry redaction, and automatic rollout rollback.

### PIR-15

Benchmark runner executes both arms through normal Atlas with identical model, repository seed, requirement, budgets, tools, and retry limits. Use a versioned corpus and repeated trials for stochastic models.

Metrics come from actual logs/artifacts. Retirement requires real consumer-zero, parity or documented superiority, rollback proof, real E2E, data migration verification, and updated status/docs.

## 5. Mandatory fault catalog

```text
SQLite busy or corrupt copy
parser syntax failure
parser/LSP unavailable
source change during planning or generation
source change after apply before verification
projection exception and duplicate event
refresh worker crash and process restart
verification collector exception
command unavailable or timeout
runtime start unhealthy
Blueprint activation race
mapping ambiguity
checkpoint replay
telemetry failure
rollout threshold breach
```

Each test states whether canonical work succeeds, degrades, retries, blocks, or rolls back.

## 6. Performance evidence

Record:

```text
files/LOC/languages
full build and incremental refresh time
node/edge/fact counts
database size
context tokens and latency
impact/test-selection latency
Convergence full/incremental latency
planning/generation overhead
observation ingestion latency
memory peak
```

Run against a small fixture, medium multi-language fixture, and KasaneCore or an equivalent real repository. Promotion thresholds are versioned before rollout.

## 7. Required evidence record

After each package record:

```text
package and status level
commit/PR
platform and runtime versions
commands and exact results
duration
fixture/repository revision
relevant artifact/revision IDs
CI or artifact reference
unavailable checks
known limitations
next package
```

## 8. Completion gates

- **Component gate:** focused/conformance/fault tests pass.
- **Production gate:** real Atlas caller invokes it; off/shadow/active and rollback pass.
- **Operational gate:** real workspace/commands/restart/platform evidence exists where required.
- **Program gate:** all PIR-0..PIR-15 acceptance criteria and the recovery master Definition of Done pass.

Synthetic-only evidence cannot close the program.
