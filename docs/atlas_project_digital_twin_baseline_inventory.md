# Atlas Project Digital Twin — Baseline and Boundary Inventory (PDT-0)

> Generated for PDT-0. Records current implementation facts before any production change.
> Source of truth is current code and tests; this document only summarizes them.
> Locate code by the listed symbols, not by line numbers.

## 1. Scope and method

This inventory inspects the existing KasaneCore codebase for the capabilities the
Project Digital Twin (PDT) goal depends on. For each capability it records:

- current capability;
- authoritative owner;
- relevant files and symbols;
- known duplication;
- reusable contracts;
- missing behavior;
- migration risk;
- test evidence;
- proposed PDT package destination.

No production path is modified by PDT-0. The only new artifacts are this document and
`tests/test_project_twin_baseline.py`, a read-only regression fixture that pins the
current public surface so later PDT packages cannot silently break it.

## 2. Top-level boundaries observed

- Production ASGI app is `main:app` (`main.py`). New routers register through
  `app/server.py:include_routers()`; lifespan/middleware/direct routes stay in `main.py`.
- Atlas agent services live under `agent/` (flat module layout, `agent/atlas_*` plus core
  files like `context_builder.py`, `memory.py`, `session.py`).
- Runtime/host features live under `app/` (`app/atlas/`, `app/nexus/`, `app/portal/`,
  `app/lumen/`, `app/api/`).
- Persistence is **JSON-file-per-record under `ca_data/`** for Atlas stores
  (repo index, plan pool, runs, conversations, memory long-term). The only existing
  **SQLite** usage is Nexus (`app/nexus/db.py`). There is **no** `agent/project_twin`
  package and **no** `ProjectTwin*` symbol anywhere yet (verified by search).

## 3. Capability inventory

### 3.1 Repository indexing

- **Current capability**: Indexes a project's files into JSON index runs; supports
  route/path discovery heuristics.
- **Authoritative owner**: `agent/atlas_repo_index_service.py:AtlasRepoIndexService`,
  persisted via `agent/atlas_repo_index_storage.py:AtlasRepoIndexStorage` (JSON under
  `ca_data/`), schema `agent/atlas_repo_index_schema.py`, policies
  `agent/atlas_repo_index_policies.py`.
- **Known duplication**: file iteration also exists in
  `agent/atlas_code_explorer.py:_iter_project_files` and `AtlasCodeIntelService`.
- **Reusable contracts**: repo index schema; index-run JSON shape.
- **Missing behavior**: no revisioned node/edge graph, no provenance/confidence,
  no incremental invalidation of derived facts.
- **Migration risk**: low — projection only; PDT reads, does not replace.
- **Test evidence**: `tests/test_atlas_repo_index_*` (existing).
- **PDT destination**: PDT-3 (structural graph source), PDT-0 baseline pin.

### 3.2 Symbol and dependency extraction / call graph

- **Current capability**: Python symbol index (class/function/method/import via `ast`),
  dependency (import) graph, related-test discovery — already deterministic.
- **Authoritative owner**: `agent/atlas_code_intel_service.py`
  (`_PythonSymbolVisitor`, `AtlasCodeIntelService.build_symbol_index`,
  `build_dependency_graph`, `find_related_tests`), schema
  `agent/atlas_code_intel_schema.py`. Lighter heuristic variant in
  `agent/atlas_code_explorer.py` (`extract_symbols`, `find_related_tests`,
  `search_code_excerpts`).
- **Known duplication**: symbol extraction and related-test discovery exist in **both**
  `atlas_code_intel_service.py` and `atlas_code_explorer.py`.
- **Reusable contracts**: `AtlasSymbolIndexRequest`, `AtlasDependencyGraphRequest`,
  `AtlasRelatedTestsRequest` and their result models.
- **Missing behavior**: no inheritance/call edges beyond imports, no JS/HTML linking,
  no canonical_ref identity, no revision/provenance.
- **Migration risk**: low — wrap, do not modify; PDT-3 adapts these into typed nodes.
- **Test evidence**: `tests/test_atlas_code_intel_service.py` (7 passed locally).
- **PDT destination**: PDT-3 (primary static source), reuse via adapter.

### 3.3 API route discovery

- **Current capability**: Route/path heuristics inside repo index service/policies.
- **Authoritative owner**: `agent/atlas_repo_index_service.py` +
  `agent/atlas_repo_index_policies.py` (route extraction); FastAPI registration in
  `app/server.py:include_routers()` and `main.py`.
- **Reusable contracts**: repo index route entries.
- **Missing behavior**: no FastAPI route → handler → service projection as graph nodes.
- **Migration risk**: low.
- **PDT destination**: PDT-3 (FastAPI route projection).

### 3.4 Related-test discovery

- **Current capability**: maps implementation files/symbols to candidate tests.
- **Authoritative owner**: `agent/atlas_code_explorer.py:find_related_tests`,
  `agent/atlas_code_intel_service.py` related-tests, and
  `agent/atlas_test_impl_linker.py:find_implementation_item`.
- **Known duplication**: three related-test/impl-link mechanisms.
- **Reusable contracts**: `AtlasRelatedTestsRequest`.
- **Missing behavior**: not linked to requirements/runtime evidence.
- **PDT destination**: PDT-3 (test nodes), PDT-4 (test↔delivery), PDT-11 (recommended tests).

### 3.5 ContextBuilder / prompt-context injection

- **Current capability**: builds bounded prompt context, file summary cache, tool-result
  cache, token estimation/truncation.
- **Authoritative owner**: `agent/context_builder.py`
  (`ContextBuilder`, `TaskV2ContextBuilder`, `FileSummaryCache`, `ToolResultCache`,
  `_estimate_tokens`, `_truncate_to_token_budget`). Repo/Nexus context in
  `agent/atlas_repo_context_service.py:AtlasRepoContextService`,
  `agent/nexus_context_builder.py`.
- **Reusable contracts**: token estimation/truncation helpers; file-summary cache.
- **Missing behavior**: no phase-aware twin slice, no per-item inclusion reason/provenance,
  no confidence/freshness filtering.
- **Migration risk**: medium — PDT-5 Context Broker must be additive and **disabled by
  default**; existing context paths must keep working unchanged.
- **Test evidence**: `tests/test_atlas_context_refresh_*` (existing).
- **PDT destination**: PDT-5 (Context Broker pilot adapter, non-replacing).

### 3.6 Project investigation

- **Current capability**: inspects a project (structure/signals) for the agent.
- **Authoritative owner**: `agent/atlas_project_inspection_service.py:AtlasProjectInspectionService`,
  `agent/atlas_git_inspection_service.py`.
- **PDT destination**: PDT-3/PDT-9 (Project Investigation Agent refresh source).

### 3.7 Requirement tracing

- **Current capability**: traces requirements to files/items with status from explicit
  evidence; keyword matching.
- **Authoritative owner**: `agent/atlas_requirement_tracer.py:AtlasRequirementTracer`
  (`_status_from_explicit_evidence`), `agent/requirement_analyzer.py`,
  `agent/requirement_schema.py`.
- **Reusable contracts**: requirement schema, tracer status outputs.
- **Missing behavior**: no `Conversation → Requirement → Plan → … → Evidence` graph with IDs.
- **PDT destination**: PDT-4 (intent and delivery trace).

### 3.8 PlanPool / PlanItem / proposal / run / verification storage

- **Current capability**: full planning/execution storage.
- **Authoritative owner**:
  - PlanPool: `agent/atlas_plan_pool_storage.py:AtlasPlanPoolStorage` (JSON per pool),
    schema `agent/atlas_plan_pool_schema.py`, builder `agent/atlas_plan_pool_builder.py`.
  - Plans: `agent/plan_storage.py`, `agent/plan_schema.py`.
  - Proposals: `agent/atlas_patch_proposal_service.py`/`_schema.py`,
    `agent/patch_storage.py`, `agent/patch_schema.py`.
  - Runs: `agent/run_storage.py:RunStorage`.
  - Verification: `agent/verification_runner.py`, `agent/verification_schema.py`,
    `agent/atlas_verification_*` (gate/recommendation/resolver),
    `agent/atlas_verification_allowlist.py`.
- **Authority note**: PlanPool/workflow are **authoritative for planning/execution**;
  PDT only projects references and must never mutate workflow state or PlanPool authority.
- **Reusable contracts**: plan pool/plan/patch/run/verification schemas.
- **PDT destination**: PDT-4 (projection), read-only.

### 3.9 Runtime / Playwright / browser / Atlas Play observations

- **Current capability**: Playwright smoke verification, visual artifact verification,
  Atlas Play runtime (sessions, console/logs, proxy) from the completed PPC work.
- **Authoritative owner**: `agent/atlas_playwright_smoke_verifier.py:AtlasPlaywrightSmokeVerifier`,
  `agent/atlas_visual_artifact_verifier.py`, `app/atlas/play/` (sessions/supervisor).
- **Missing behavior**: observations are not normalized into `RuntimeObservation` records
  with pass/fail/unavailable and evidence links.
- **PDT destination**: PDT-9 (runtime collectors), PDT-10 (reconciliation).

### 3.10 HybridMemoryStore

- **Current capability**: short-term ring buffer + pluggable long-term saver/searcher;
  durable memory item shapes (ArchitectureDecision, TaskOutcome, ModuleMap, RiskRegister).
- **Authoritative owner**: `agent/memory.py`
  (`MemoryStore`, `HybridMemoryStore`, and the dataclasses above).
- **Reusable contracts**: memory item dataclasses; `store_memory`/`retrieve_memory` API.
- **Missing behavior**: no verified-promotion gate, no supersede/invalidate history,
  no project-scoped recall guarantees tied to the twin.
- **Migration risk**: medium — PDT-6 must adapt, not replace; unverified inference must
  not become durable memory.
- **PDT destination**: PDT-6 (memory integration via adapter).

### 3.11 Skill discovery and loading

- **Current capability**: **No Atlas-level Skill registry/loader exists.** The only
  registries are unrelated (`app/tts/engine_registry.py`, `agent/tools/registry.py`,
  `agent/atlas_visual_contract_registry.py`). `SKILL.md` assets are not yet ingested.
- **Authoritative owner**: none yet (gap).
- **Missing behavior**: registry, resolver, version/content hash, activation reason,
  outcome, safety precedence.
- **PDT destination**: PDT-7 (new Skill registry; must not expand execution authority).

### 3.12 Nexus evidence

- **Current capability**: research/evidence store with SQLite backend, citation mapping,
  reports.
- **Authoritative owner**: `app/nexus/` (`db.py` SQLite, `evidence.py`, `report.py`,
  `research_agent.py`, `schemas.py`, `router.py`); Atlas adapters
  `agent/atlas_nexus_research_adapter.py`, `agent/nexus_context_builder.py`,
  `agent/atlas_context_nexus_adapter.py`.
- **Reusable contracts**: Nexus schemas; SQLite usage precedent for PDT-2 store.
- **Authority note**: Nexus is authoritative for external documents/evidence; PDT
  references them and must never convert external claims into verified code truth.
- **PDT destination**: PDT-12 (Nexus integration).

### 3.13 Conversation / AgentSession persistence

- **Current capability**: conversation store (JSON) and in-process agent session/queue.
- **Authoritative owner**: `agent/atlas_conversation_store.py:AtlasConversationStore`,
  `agent/session.py` (`AgentSession`, `QueuedTask`).
- **Authority note**: conversation storage is authoritative for messages.
- **PDT destination**: PDT-4 (Conversation/Message references).

### 3.14 Graph / visualization components

- **Current capability**: no project-structure graph visualization. Front-end has the
  Atlas pipeline API (`web/js/atlas_pipeline_api.js`) and Portal UI, but no twin graph view.
- **Authoritative owner**: none yet (gap).
- **PDT destination**: PDT-13 (Project Twin API and UI).

## 4. Authoritative ownership map (summary)

| Domain source | Authoritative owner | PDT relation |
|---|---|---|
| Code / workspace | Git + workspace, `AtlasRepoIndexService`, `AtlasCodeIntelService` | projected (PDT-3) |
| Messages | `AtlasConversationStore` | referenced (PDT-4) |
| Planning / execution | PlanPool/workflow stores | referenced, never mutated (PDT-4) |
| External evidence | Nexus (`app/nexus`) | referenced (PDT-12) |
| Durable memory | `HybridMemoryStore` | adapted (PDT-6) |
| Skill definitions | none yet | new registry (PDT-7) |
| Runtime evidence | Playwright/visual/Play | normalized collectors (PDT-9) |

## 5. Known duplication / legacy paths

- Symbol + related-test extraction duplicated across `atlas_code_intel_service.py`,
  `atlas_code_explorer.py`, and `atlas_test_impl_linker.py`. PDT must pick one
  authoritative static source (CodeIntel) and adapt others; **do not delete** duplicates
  before parity and migration evidence (per agent entrypoint scope discipline).
- File iteration duplicated across repo index, code explorer, code intel.

## 6. Migration constraints

- Atlas stores are JSON-file-based; the PDT SQLite store (PDT-2) is a **new, isolated**
  store under a replaceable `ProjectTwinPort`. It must not migrate or rewrite existing
  JSON stores. Nexus (`app/nexus/db.py`) is the SQLite precedent to follow.
- Per-project isolation must be enforced at the store layer (`project_id` scoping).
- All PDT writes are additive projections; canonical systems remain authoritative.

## 7. Safety invariants confirmed unchanged by PDT-0

PDT-0 adds only a document and a read-only test. It does not touch workflow state,
PlanPool authority, approval/critical-event gates, allowed paths, Safe Apply, rollback,
retry limits, command allowlists, remote-push/merge restrictions, truthful verification,
or project isolation.

## 8. Regression fixtures and benchmark scenarios

- Regression fixture: `tests/test_project_twin_baseline.py` pins:
  - importability of the inventoried owners;
  - deterministic Python symbol indexing via `AtlasCodeIntelService`;
  - deterministic dependency-graph edge prefixes;
  - HybridMemoryStore short-term recall behavior;
  - absence of a `project_twin` package (so PDT-1 introduction is an explicit, reviewed step).
- Initial PDT benchmark scenarios (for PDT-14) are enumerated in the implementation plan
  (function impact, UI-to-persistence trace, requirement trace, API side effects,
  static/runtime contradiction, test recommendation, design history, incident history,
  project isolation, token-bounded context, incremental refresh, memory promotion,
  skill activation, Nexus evidence). The baseline test records that none are implemented yet.

## 9. Acceptance check (PDT-0)

- Current behavior of the primary reused services is covered by an executed test.
- No production path is replaced.
- Next package (PDT-1) target files are explicit:
  `agent/project_twin/contracts.py`, `types.py`, `events.py`, `versioning.py`,
  `tests/test_project_twin_contracts.py`.
