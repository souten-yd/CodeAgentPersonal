# Atlas Project Digital Twin Architecture

## 1. Purpose

This document defines the target architecture and component boundaries for the Project Digital Twin.

The implementation must preserve KasaneCore's interface-first rule:

> All cross-component integration uses explicit, versioned public contracts. Direct dependency on another component's private storage or internal objects is prohibited.

## 2. System context

```text
Git / Workspace --------------------+
Conversation Store -----------------+
PlanPool / Atlas Runtime -----------+
Nexus Store ------------------------+--> Twin Ingestion Layer
Memory Store -----------------------+        |
Skill Registry ---------------------+        v
Runtime Collectors -----------------+   Project Twin Store
                                             |
                      +----------------------+-------------------+
                      |                      |                   |
                Query Service         Impact Service      Context Broker
                      |                      |                   |
                Project Twin UI      Planner/Verifier     Atlas Agents
```

## 3. Source-of-truth ownership

| Domain | Canonical owner | Twin responsibility |
|---|---|---|
| Code | Git/workspace | identity, symbols, relations, revision |
| Conversation | Conversation Store | provenance links and summaries |
| Requirements/Plans | PlanPool/workflow storage | delivery trace projection |
| Runtime execution | Atlas runtime/journal | observations and run links |
| External evidence | Nexus | evidence references and relations |
| Durable memory | Memory Store | evidence and supersession relations |
| Skills | Skill files/registry | applicability, activation and outcome |
| Graph relations | Project Twin Store | canonical normalized relation projection |

Twin deletion must not delete canonical source content unless an explicit source-domain operation is invoked.

## 4. Component boundaries

### 4.1 Twin Contract Package

Suggested location:

```text
agent/project_twin/contracts.py
agent/project_twin/types.py
agent/project_twin/events.py
agent/project_twin/versioning.py
```

Responsibilities:

- stable schemas;
- enums;
- public ports;
- serialization;
- contract version negotiation;
- compatibility validation.

Must not:

- access SQLite;
- parse source files;
- call LLMs;
- import UI modules.

### 4.2 Twin Store

Suggested location:

```text
app/project_twin/repository.py
app/project_twin/sqlite_repository.py
app/project_twin/migrations/
app/project_twin/transaction.py
```

Responsibilities:

- projects;
- revisions;
- nodes;
- edges;
- evidence;
- observations;
- snapshots;
- delta transactions;
- project isolation;
- idempotency;
- stale-revision protection.

### 4.3 Static Analysis Adapters

Suggested location:

```text
agent/project_twin/static_analysis/base.py
agent/project_twin/static_analysis/python_ast.py
agent/project_twin/static_analysis/javascript.py
agent/project_twin/static_analysis/html_css.py
agent/project_twin/static_analysis/manifest.py
agent/project_twin/static_analysis/lsp_adapter.py
```

Initial mandatory support:

- Python files/modules/classes/functions/methods;
- imports;
- inheritance;
- basic calls;
- FastAPI routes;
- tests and fixtures;
- HTML script/style references;
- basic JS imports/event handlers where current parsers allow.

Language adapters return typed deltas. They do not write the store directly.

### 4.4 Delivery Projectors

Suggested location:

```text
agent/project_twin/projectors/conversation.py
agent/project_twin/projectors/requirements.py
agent/project_twin/projectors/plan_pool.py
agent/project_twin/projectors/proposals.py
agent/project_twin/projectors/verification.py
```

Responsibilities:

- create links across intent and delivery;
- preserve source IDs;
- detect missing traceability;
- publish typed projection deltas.

### 4.5 Behavior Model

Suggested location:

```text
agent/project_twin/behavior/schema.py
agent/project_twin/behavior/static_inference.py
agent/project_twin/behavior/reconciliation.py
agent/project_twin/behavior/side_effects.py
```

Behavior node types:

- Event
- Action
- State
- StateTransition
- DataSource
- DataTransform
- DataSink
- SideEffect
- APIRequest
- APIResponse
- DBOperation
- FileOperation
- NetworkOperation
- ProcessOperation
- UIInteraction
- RenderOperation
- Failure
- Recovery

Behavior relations:

- `TRIGGERS`
- `CALLS`
- `READS`
- `WRITES`
- `TRANSFORMS`
- `TRANSITIONS_TO`
- `EMITS`
- `PERSISTS_TO`
- `SENDS_TO`
- `RENDERS`
- `FAILS_WITH`
- `RECOVERED_BY`

### 4.6 Runtime Collectors

Suggested location:

```text
agent/project_twin/runtime/base.py
agent/project_twin/runtime/pytest_collector.py
agent/project_twin/runtime/playwright_collector.py
agent/project_twin/runtime/api_collector.py
agent/project_twin/runtime/observation_normalizer.py
```

Collectors must be:

- bounded;
- opt-in where instrumentation is intrusive;
- project-scoped;
- non-authoritative until evidence is persisted;
- truthful about unavailable instrumentation.

Initial collectors:

1. pytest result and selected test-to-symbol evidence;
2. Playwright page/console/request evidence;
3. Atlas Play console/failed-request observations;
4. API request/response contract observations.

### 4.7 Context Broker

Suggested location:

```text
agent/project_twin/context_broker.py
agent/project_twin/context_policy.py
agent/project_twin/context_ranker.py
agent/project_twin/context_budget.py
```

Inputs:

- project ID;
- objective;
- phase;
- PlanPool/PlanItem IDs;
- target files/symbols;
- token budget;
- confidence threshold;
- freshness policy;
- requested domains.

Outputs:

- requirement context;
- related symbols/files;
- call and behavior paths;
- side effects;
- related tests;
- runtime observations;
- past incidents;
- durable memories;
- applicable skills;
- Nexus evidence;
- preserve-behavior rules;
- uncertainty diagnostics;
- inclusion/exclusion reasons.

Direct access from Planner/Generator/Verifier to private graph storage is forbidden.

### 4.8 Query and Impact Services

Suggested location:

```text
app/project_twin/query_service.py
app/project_twin/path_service.py
app/project_twin/impact_service.py
app/project_twin/health_service.py
```

Impact categories:

- direct structural;
- transitive call/reference;
- behavior/state;
- side effect;
- requirement;
- verification/test;
- operational/configuration;
- historical risk.

Impact output must contain explanation paths, not only a score.

### 4.9 API

Suggested location:

```text
app/api/project_twin.py
```

Initial endpoints:

```text
GET  /api/project-twin/projects/{project_id}/health
GET  /api/project-twin/projects/{project_id}/revisions
GET  /api/project-twin/projects/{project_id}/nodes
GET  /api/project-twin/projects/{project_id}/nodes/{node_id}
GET  /api/project-twin/projects/{project_id}/nodes/{node_id}/neighbors
POST /api/project-twin/projects/{project_id}/query
POST /api/project-twin/projects/{project_id}/path
POST /api/project-twin/projects/{project_id}/impact
POST /api/project-twin/projects/{project_id}/context
POST /api/project-twin/projects/{project_id}/refresh
```

Mutation endpoints that affect project code remain in existing Atlas authorities.

### 4.10 UI

Suggested location:

```text
web/js/project_twin_api.js
web/js/project_twin_state.js
web/js/project_twin_ui.js
```

Views:

- Structure
- Behavior
- Delivery
- History
- Impact

UI rules:

- display/query only;
- lazy neighbor expansion;
- bounded initial graph;
- filters for status/confidence/revision/type;
- source navigation;
- never grants execution authority.

## 5. Identity model

### 5.1 Project identity

`project_id` must derive from the selected project record, not raw filesystem path alone.

A project may move paths without losing historical identity.

### 5.2 Canonical references

Examples:

```text
file://src/service.py
python://src.service/UserService
python://src.service/UserService.save
api://POST /api/users
db://main/users
requirement://REQ-123
planitem://pool_x/item_y
test://tests/test_users.py::test_save
skill://browser-game-verification@1.2.0
memory://architecture_decision/<id>
```

Canonical reference builders are versioned and deterministic.

### 5.3 Revision identity

A twin revision records:

- parent revision;
- source Git commit when available;
- working tree fingerprint;
- parser/tool versions;
- changed nodes/edges;
- invalidations;
- timestamp;
- triggering event/run.

## 6. Provenance and confidence

Every fact has:

- `source_kind`
- `source_ref`
- `source_revision`
- `derivation`
- `evidence_refs`
- `confidence`
- `status`
- `valid_from`
- `valid_to`

Suggested confidence rules:

| Origin | Initial confidence |
|---|---:|
| canonical declared record | 0.95 |
| deterministic AST relation | 0.90 |
| heuristic static inference | 0.55–0.80 |
| LLM inference | 0.35–0.70 |
| runtime observation | 0.90 |
| repeated runtime observation | 0.95 |
| verified test/evidence mapping | 0.98 |
| stale source revision | reduce by policy |

Confidence is not a substitute for status.

## 7. Delta processing

### 7.1 Typed delta

A `TwinDelta` contains:

- base revision;
- trigger;
- source changes;
- node upserts;
- edge upserts;
- invalidations;
- observation additions;
- evidence additions;
- diagnostics;
- idempotency key.

### 7.2 Stale revision handling

If the base revision is stale:

1. do not overwrite newer facts blindly;
2. load current affected entities;
3. rebase/recompute the affected delta;
4. retry within bounds;
5. return `needs_refresh` if unresolved.

### 7.3 Event-driven updates

Typed events include:

- `workspace.changed`
- `safe_apply.completed`
- `plan_item.completed`
- `verification.completed`
- `runtime_observation.recorded`
- `conversation.message.completed`
- `requirement.confirmed`
- `memory.promoted`
- `skill.registered`
- `skill.activated`
- `nexus.evidence.added`

Consumers may subscribe through an internal event dispatcher, but events remain data contracts, not direct service calls.

## 8. Conversation integration

Conversation store schema must support:

- sessions;
- messages;
- parent/branch relation;
- project and surface;
- run/plan/artifact references;
- streaming status;
- summaries;
- archive/delete/export.

The twin stores message identity and semantic relations, not duplicate full history unless explicitly projected.

## 9. Memory integration

Existing `HybridMemoryStore` remains reusable behind an adapter.

Memory lifecycle:

```text
observed
-> inferred
-> verified or user-approved
-> durable
-> superseded/invalidated
```

Durable promotion requires evidence policy.

Memory retrieval must include:

- project scope;
- category;
- confidence;
- freshness;
- evidence;
- supersession status.

## 10. Skill integration

Existing `ca_data/skills/<name>/SKILL.md` remains canonical.

Registry metadata:

- ID and version;
- task/file applicability;
- required tools;
- allowed operations;
- verification requirements;
- compatibility;
- content hash;
- activation history;
- outcome/effectiveness.

Selection priority:

1. user-explicit;
2. project-pinned;
3. task classification;
4. file/technology match;
5. verified historical success.

Skills cannot modify safety authority.

## 11. Nexus integration

Twin relations:

- Evidence `SUPPORTS` Requirement/Decision/Risk;
- Evidence `CONTRADICTS` Assumption/Decision;
- Document `CONTAINS` Evidence;
- Report `SUMMARIZES` Evidence.

External evidence stores:

- source URL/document ID;
- retrieval timestamp;
- content revision/hash;
- source type;
- confidence;
- citation span.

## 12. Performance requirements

Initial targets:

- no full rebuild for ordinary single-file updates;
- bounded graph query depth by default;
- paginated node/edge results;
- background refresh separate from request path where safe;
- context construction bounded by tokens and wall-clock timeout;
- health API reports queue/backlog/stale state;
- graph UI loads small projections only.

## 13. Security and privacy

- project-scoped database and queries;
- path canonicalization;
- no secret content in graph properties by default;
- redact environment values;
- runtime collectors use allowlists;
- no arbitrary command execution introduced;
- source navigation respects allowed paths;
- conversation deletion policy propagates relation invalidation;
- export clearly marks sensitive metadata.

## 14. Observability

Record:

- ingestion job;
- source count;
- node/edge delta;
- invalidation count;
- parse errors;
- collector availability;
- stale regions;
- query latency;
- context token usage;
- confidence distribution;
- failed reconciliation.

Observability must not expose secrets.

## 15. Migration and compatibility

- introduce alongside current Repo Index/CodeIntel;
- adapt existing information into typed deltas;
- do not remove legacy components until parity tests pass;
- add compatibility readers where needed;
- remove duplicate paths only in a dedicated cleanup work package;
- preserve current Atlas behavior during rollout.

## 16. Failure policy

- parser failure: record degraded coverage, continue unaffected adapters;
- store transaction failure: no partial revision;
- collector unavailable: report unavailable, do not fabricate;
- context timeout: return bounded partial context with diagnostics;
- conflicting facts: retain contradiction explicitly;
- migration failure: fail closed and preserve prior database.
