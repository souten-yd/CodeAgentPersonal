# Atlas Project Intelligence — Decision Register

Status: canonical accepted decisions.

This register freezes the architectural decisions agreed for the Project Intelligence program. Implementers must not reopen these decisions casually. A change requires an explicit document revision, impact analysis, migration plan, and current-status entry.

## ADR-PI-001 — Actual, target, and comparison are separate

Decision:

```text
Actual Project Twin = what actually exists or was observed
Architecture Blueprint = what should exist
Convergence = comparison between the two
```

Consequences:

- planned files and symbols never use Actual namespaces before materialization;
- Blueprint approval does not imply implementation or verification;
- Digital Twin does not decide target architecture;
- Convergence does not mutate either side.

## ADR-PI-002 — Module-level isolation

Decision:

Public isolation is at module level, not at every helper function.

Required facades:

```text
DigitalTwinModule
ArchitectureBlueprintModule
ConvergenceModule
ProjectIntelligenceModule
```

Consequences:

- graph micro-capabilities remain Digital Twin internals;
- matcher/evaluator/policy remain Convergence internals;
- generator/reviewer/store remain Blueprint internals;
- external consumers use coarse context/result packages.

## ADR-PI-003 — Digital Twin is not execution authority

Decision:

Digital Twin, Blueprint, Convergence, and Project Intelligence never bypass PlanPool, approval, Safe Apply, command authority, rollback, or verification.

Consequences:

- projections are advisory/read models;
- Convergence decisions are recommendations/policy outputs, not mutations;
- Safe Apply and verification remain canonical boundaries.

## ADR-PI-004 — Canonical systems remain authoritative

Decision:

Requirements, conversations, PlanPool, proposals, Safe Apply, verification, Nexus, Memory, Skills, and Atlas Play retain their canonical stores and authority.

Consequences:

- Project Intelligence stores references/projections, not competing canonical copies;
- canonical writes complete before event projection;
- projection failure cannot rewrite a successful canonical result.

## ADR-PI-005 — Existing PDT-0..14 are Core v1, not final completion

Decision:

PDT-0 through PDT-14 remain completed historical packages and are not restarted. They provide Core v1 foundations. The active program is PI-0 through PI-25.

Consequences:

- old documents remain reference material;
- `atlas_project_intelligence_current_status.md` is the active checkpoint;
- Codex must not begin from PDT-0.

## ADR-PI-006 — Deep graph implementation is mandatory

Decision:

Name-based call edges, regex-only frontend analysis, and coarse side-effect categories are compatibility behavior, not final Graph Intelligence.

Mandatory eventual capabilities:

- structural and semantic graphs;
- resolved/candidate call graph;
- control flow;
- data flow;
- state/event/recovery;
- concrete resources and side effects;
- API/schema/DB/config/dependency/UI/rendering relations;
- runtime trace and reconciliation;
- path, impact, and test selection.

## ADR-PI-007 — Blueprint before broad Greenfield generation

Decision:

An empty or nearly empty project requires a reviewed/active Blueprint with an exact file manifest and execution contracts before broad multi-file generation.

Consequences:

- vague “create necessary files” plans are invalid;
- generation follows Blueprint dependency order;
- Actual Twin refresh and Convergence run after each coherent slice;
- Greenfield still uses normal PlanPool, Proposal, Safe Apply, and Verification.

## ADR-PI-008 — Planner becomes a gap compiler/strategy layer

Decision:

Planner remains central but operates on Requirement + Actual Twin + Blueprint + Convergence.

Roles:

```text
Architecture Planner
Delivery Planner
Repair Planner
```

Deterministic code owns identity, dependency order, requirement mapping, completed-item preservation, and target normalization. LLMs own architecture recommendations and implementation strategy within contracts.

## ADR-PI-009 — Partial replanning before whole replanning

Decision:

Convergence selects the smallest valid response:

```text
continue
repair current item
replan downstream
revise Blueprint
critical decision
safe halt
complete
```

Consequences:

- local defects do not recreate the whole PlanPool;
- completed items remain stable;
- Blueprint revision is reserved for target-design invalidity or approved design change.

## ADR-PI-010 — Existing capabilities are reorganized, not permanently duplicated

Decision:

Existing project analysis, context, impact, test recommendation, trace, and runtime normalization are migrated through KEEP/ADAPT/REPLACE/REMOVE classification.

Consequences:

- facades and compatibility adapters precede cutover;
- shadow comparison precedes authority change;
- legacy deletion follows consumer-zero and parity gates;
- no new direct dependency on a legacy path after its facade exists.

## ADR-PI-011 — Event projection uses outbox/journal semantics

Decision:

Canonical operations emit durable events after successful canonical writes. Project Intelligence consumes them at least once with idempotency.

Consequences:

- no unsafe dual-write transaction across unrelated stores;
- retryable projection jobs survive restart;
- duplicate events are harmless;
- canonical success is retained when projection is degraded.

## ADR-PI-012 — Revision identity is mandatory in context and evidence

Decision:

Planning, generation, verification, repair, and Convergence artifacts record relevant Actual Twin, Blueprint, source, and report revisions.

Consequences:

- stale context is detectable;
- old runtime evidence cannot verify new source;
- resume revalidates revisions before continuing;
- Context Manifest is required for active consumers.

## ADR-PI-013 — Unavailable is never passed

Decision:

Unavailable parsers, collectors, browsers, runners, environments, or platforms remain explicitly unavailable.

Consequences:

- no completion from missing instrumentation;
- Convergence leaves required evidence incomplete;
- status records exactly what was not verified.

## ADR-PI-014 — Portable core, Atlas adapters outside

Decision:

The four modules must be instantiable without Atlas workflow, FastAPI, UI, or PlanPool imports.

Consequences:

- Atlas integration code lives in adapters/composition root;
- portable cores use public DTOs;
- standalone construction is contract-tested;
- storage/analyzer implementations are replaceable behind module internals.

## ADR-PI-015 — SQLite is an adapter, not the public architecture

Decision:

SQLite is the initial persistence implementation for module artifacts, but no consumer depends on its tables.

Consequences:

- public facades return DTOs only;
- Convergence and Planner cannot query SQLite directly;
- persistence can later be replaced without consumer changes.

## ADR-PI-016 — Context is delivered as phase packages

Decision:

Planner and Generator receive one coherent package per phase rather than calling many graph micro-ports.

Required packages:

```text
PlanningContextPackage
GenerationContextPackage
```

Consequences:

- inclusion/exclusion reasons and token budget are centralized;
- every active package has a Context Manifest;
- graph internals remain hidden.

## ADR-PI-017 — Rollout is phased and reversible

Decision:

Rollout proceeds through off, shadow, planning, generation, verification, repair, supervised Greenfield, and full active stages.

Consequences:

- each stage has telemetry and rollback;
- old environment variables remain compatibility inputs temporarily;
- legacy removal occurs only after final active parity.

## ADR-PI-018 — Tests and real E2E define implementation completeness

Decision:

Classes, schemas, and synthetic benchmarks alone do not prove implementation.

Consequences:

- production/shadow wiring is required;
- fault and restart behavior are tested;
- Greenfield E2E begins from normal Atlas entrypoints;
- exact executed evidence is recorded per work package.

## ADR-PI-019 — Change-control process

A frozen decision may change only through all of the following:

1. identify the ADR and reason for change;
2. inspect current implementation and consumers;
3. provide alternatives and tradeoffs;
4. describe contract, persistence, migration, safety, test, and rollout impacts;
5. create a replacement or amended ADR;
6. update master goal/architecture/contracts/plan as necessary;
7. update current status before implementation;
8. preserve backward compatibility or provide an approved migration.

A model preference, implementation convenience, or temporary test failure is not sufficient reason to reverse a decision.
