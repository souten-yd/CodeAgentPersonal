# Atlas Project Digital Twin Goal

> Status: Active P0 canonical goal  
> Execution target: Codex or Claude  
> Work package sequence: `PDT-0` through `PDT-14`  
> Source of truth: current code, tests, and the Project Digital Twin canonical documents

## 1. Final goal

Atlas shall maintain each selected project as a continuously updated, revisioned **Project Digital Twin** rather than treating the repository as a flat collection of files.

The twin connects:

- repository, directory, file, module and package structure;
- symbols, types, inheritance, imports, references and call relationships;
- data flow, state transitions, events and side effects;
- API, database, file, process, network and UI behavior;
- runtime observations from tests, Playwright, browser, API and safe collectors;
- `Conversation -> Requirement -> Plan -> PlanItem -> Proposal -> Code -> Test -> Verification -> Evidence`;
- architecture decisions, incidents, root causes, repairs and risks;
- durable Memory, reusable Skill and Nexus evidence.

The twin must be built before implementation work where possible, updated incrementally after relevant changes, and queried only through stable public interfaces.

Atlas agents must receive the smallest evidence-backed context slice required for their current phase.

## 2. Target capabilities

When complete, Atlas must answer with sources, revisions and confidence:

1. What may break if this function, class, route, schema or file changes?
2. How does a UI action flow through frontend code, API, service, persistence and response rendering?
3. Where is a requirement implemented, and which tests and runtime observations verify it?
4. Which code paths perform database, file, network, process or UI side effects?
5. Which static assumptions are confirmed or contradicted by runtime evidence?
6. Why was a design selected, what alternatives were rejected, and which incidents influenced it?
7. Which memories and skills are relevant to a task, and why were they selected?
8. Which parts of project understanding are stale, incomplete or low-confidence?
9. Which tests should run for a proposed change?
10. Which existing behavior must be preserved?

## 3. Twin domains

### 3.1 Structural Twin

Represents repository structure and static semantics:

- Repository, Directory, File, Package, Module
- Class, Function, Method, Variable, Constant, Type
- Import, Reference, Inheritance, Implementation, Call
- API Route, Request/Response Schema, Service
- Database Table, Migration, Query
- Configuration, Environment Variable
- Test, Fixture, Command

### 3.2 Behavioral Twin

Represents expected and inferred behavior:

- Event, Action, State, Transition
- Data Source, Transformation, Sink
- API request/response flow
- Database, file, network and process side effects
- UI interaction and rendering flow
- Error, recovery and retry flow

### 3.3 Runtime Twin

Represents observed behavior:

- Test execution and result
- Playwright/browser trace
- API request and response observation
- Browser console and failed request
- Safe function/service trace where available
- Database, file and network observation
- Exception and performance evidence

### 3.4 Intent and Delivery Twin

Represents delivery traceability:

- Conversation and Message
- Requirement and Constraint
- Architecture Decision
- Plan, PlanItem and Dependency
- Proposal, Apply Result and Run
- Changed File and Symbol
- Test, Verification and Evidence

### 3.5 Learning Twin

Represents reusable project knowledge:

- Durable Memory
- Architecture Decision
- Task Outcome
- Module Map
- Risk and Known Failure Pattern
- Incident, Root Cause and Repair
- Skill Definition, Version, Activation and Outcome
- Nexus Document, Evidence and Report

## 4. Architectural principles

### 4.1 Public interfaces first

Boundary interfaces and versioned contracts must be defined and contract-tested before implementation details.

No consumer may depend on private database tables, internal graph classes or unversioned serialized payloads.

### 4.2 Canonical systems remain authoritative

The twin is a revisioned projection and relation model, not a replacement for every source system.

- Git/workspace is authoritative for code.
- Conversation storage is authoritative for messages.
- PlanPool and workflow storage are authoritative for planning/execution.
- Nexus storage is authoritative for source documents and external evidence.
- Memory storage is authoritative for durable memories.
- Skill files and registry are authoritative for skill definitions.

The twin stores normalized identities, facts, relationships, provenance, evidence, confidence and revision history.

### 4.3 Provenance is mandatory

Every derived node and edge must identify:

- project
- source kind
- source reference
- source revision
- derivation method
- evidence references
- confidence
- validity window
- current status

The system must distinguish:

- `declared`
- `inferred`
- `observed`
- `verified`
- `user_approved`
- `contradicted`
- `superseded`
- `invalidated`

An LLM inference must never be displayed or consumed as a verified runtime fact.

### 4.4 Incremental update by default

Normal update flow:

```text
Detect delta
-> identify changed files and symbols
-> update static graph
-> invalidate affected derived facts
-> rebuild affected behavior paths
-> attach runtime evidence
-> recalculate confidence
-> publish a new twin revision
```

Full rebuild is limited to:

- initial indexing
- schema migration
- explicit maintenance
- corruption recovery
- parser version incompatibility

### 4.5 Bounded context delivery

Atlas agents must not receive the full twin.

A phase-aware Context Broker selects a bounded slice using:

- project
- objective
- phase
- current PlanItem
- target files/symbols
- confidence
- freshness
- token budget
- safety policy

Each returned item includes its source and inclusion reason.

### 4.6 Safety authority is unchanged

The twin may inform decisions but must never bypass:

- backend workflow state
- PlanPool authority
- approval and critical-event gates
- allowed paths
- Safe Apply
- rollback requirements
- retry and command limits
- remote push/direct merge restrictions
- truthful verification

### 4.7 Local-first operation

The first production backend must operate locally on:

- Windows
- Linux
- Docker
- Runpod

SQLite is the initial storage implementation behind a replaceable `ProjectTwinPort`.

## 5. Required public capabilities

The final public surface must support:

- create/open a project twin;
- obtain current revision and health;
- apply a typed delta transactionally;
- query nodes and relationships;
- trace a path between entities;
- assess change impact;
- trace requirements to implementation and evidence;
- ingest runtime observations;
- reconcile inferred and observed facts;
- build token-bounded context slices;
- register Conversation, Memory, Skill and Nexus references;
- invalidate and supersede stale facts;
- export diagnostics without exposing private implementation.

## 6. Required agent integration

### Project Investigation Agent

- builds and refreshes the twin;
- runs repository inspection and static analysis;
- uses LSP where available;
- identifies unknown/low-confidence regions;
- requests targeted runtime evidence.

### External Research Agent

- uses Nexus;
- attaches external evidence to requirements, decisions and risks;
- preserves source and retrieval date;
- never converts external claims directly into verified project truth.

### Strategy Planning Agent

- queries impact, dependencies and preserve-behavior constraints;
- plans implementation and verification from twin evidence;
- identifies missing context before execution.

### Execution Agent

- receives a bounded implementation slice;
- does not access private twin storage directly;
- records produced changes through typed events.

### Verification Agent

- records actual test/runtime evidence;
- reconciles static assumptions with observations;
- updates evidence and confidence truthfully.

## 7. Global acceptance scenarios

### A. Function impact

Given a function or method, return:

- callers and callees;
- affected behavior paths;
- related requirements;
- relevant tests;
- side effects;
- confidence and source references.

### B. UI-to-persistence trace

Given a UI control, trace:

```text
UI control
-> event handler
-> request builder
-> API route
-> service
-> database/file persistence
-> response
-> UI update
```

Distinguish inferred and observed edges.

### C. Requirement traceability

Given a requirement ID, return:

- source conversation/message;
- constraints and decisions;
- PlanItems;
- changed files and symbols;
- tests and verification evidence;
- unresolved gaps.

### D. Incremental refresh

After a single file change:

- update the relevant twin region;
- preserve unrelated revisions;
- invalidate stale derived facts;
- publish a new revision.

### E. Runtime reconciliation

When runtime evidence contradicts a static relationship:

- keep both histories;
- mark the old relationship contradicted or invalidated;
- create the observed relation with evidence;
- recalculate confidence.

### F. Memory promotion

- unverified model inference cannot become durable memory;
- verified task outcomes can be promoted with evidence;
- superseded memory remains traceable.

### G. Skill safety

- skill selection and version are recorded;
- activation reason and outcome are recorded;
- a skill cannot expand execution authority.

### H. Project isolation

No Conversation, Memory, Skill activation, graph fact or evidence leaks across project boundaries without an explicit versioned sharing policy.

### I. Token-bounded context

The Context Broker:

- remains within requested token budget;
- reports inclusion/exclusion/truncation;
- preserves essential safety and requirement facts.

### J. Truthful uncertainty

Missing coverage, stale revisions, unavailable runtime evidence and low-confidence paths are reported, not fabricated.

## 8. Definition of done

The goal is complete when:

- all mandatory work packages are completed;
- public contracts are versioned and contract-tested;
- a local transactional twin store works;
- static structure, delivery trace and runtime evidence are integrated;
- impact and path queries work against real KasaneCore scenarios;
- Atlas consumes bounded twin context through the broker;
- Conversation, Memory, Skill and Nexus retain provenance;
- stale and contradictory information is explicit;
- UI/API inspection remains non-authoritative;
- E2E acceptance scenarios have automated evidence;
- existing Atlas safety and truthful-verification invariants remain intact.
