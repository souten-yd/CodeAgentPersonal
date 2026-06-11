# Atlas Project Intelligence — Existing Capability Map (PI-0)

> Generated for PI-0 against current `main` (HEAD `0fd98c1`, PR #1648 merged).
> Read-only inventory. No production behavior is changed by PI-0.
> Locate code by the listed symbols, not by line numbers.
> Companion documents: `atlas_project_intelligence_consumer_map.md`,
> `atlas_project_intelligence_migration_matrix.md`.

## 1. Scope and method

PI-0 captures an executable baseline of the project-analysis, context, impact,
verification-support, and Project Twin behavior that the Project Intelligence program
(`PI-1..PI-25`) will reorganize behind the four module facades
(`DigitalTwinModule`, `ArchitectureBlueprintModule`, `ConvergenceModule`,
`ProjectIntelligenceModule`).

For each capability this map records:

- current capability;
- authoritative owner (symbol);
- known duplication;
- reusable contracts;
- missing behavior (relative to the master goal / ADR-PI-006 deep-graph target);
- migration risk.

Direct consumers are recorded by symbol in the companion consumer map.
KEEP/ADAPT/REPLACE/REMOVE classification is in the companion migration matrix.

This map extends and supersedes (for the Project Intelligence program) the older
`atlas_project_digital_twin_baseline_inventory.md`, which remains a historical
Core v1 reference.

## 2. Foundation status (recorded fact, not a goal restart)

- **Project Digital Twin Core v1 (`PDT-0..PDT-14`) is COMPLETE** and is **not restarted**
  (ADR-PI-005). Evidence: `docs/atlas_project_digital_twin_current_status.md`
  (Overall: COMPLETE), `agent/project_twin/` package present, 15 twin test modules.
- Core v1 provides: versioned contracts `atlas.project_twin.v1`
  (`agent/project_twin/contracts.py`), a transactional SQLite store
  (`agent/project_twin/store.py:SqliteProjectTwinStore`), static/behavioral/intent/runtime
  projection, reconciliation, impact/path analysis, context broker, memory/skill/nexus
  adapters, a read-only inspection API/UI, and a disabled-by-default rollout flag.
- Core v1 is a **foundation**, not the final program. Active gaps (per current status §
  "Important interpretation"): production wiring into real Planner/Generator/Verification
  paths; deep semantic/call/control-flow/data-flow/state/event/resource graphs;
  Architecture Blueprint; Convergence; Greenfield; capability consolidation; rollout and
  comparative benchmark.

## 3. Top-level boundaries observed

- Production ASGI app is `main:app` (`main.py`); routers register through
  `app/server.py:include_routers()`.
- Atlas agent services live under `agent/` (flat module layout: `agent/atlas_*.py`
  plus core files `context_builder.py`, `memory.py`, `session.py`).
- Runtime/host features live under `app/` (`app/api/`, `app/atlas/`, `app/nexus/`, ...).
- Persistence: JSON-file-per-record under `ca_data/` for Atlas stores; SQLite is used by
  Nexus (`app/nexus/db.py`) and by the Twin store (`agent/project_twin/store.py`).
- The four Project Intelligence module packages do **not** exist yet at PI-0
  (`agent/project_intelligence`, `agent/architecture_blueprint`,
  `agent/project_convergence`, and `agent/project_twin/facade.py` are all absent —
  pinned by the baseline test; introduced at PI-1).

## 4. Capability inventory

### 4.1 Repository enumeration / indexing

- **Current capability**: enumerates project files into JSON index runs; route/path
  discovery heuristics.
- **Authoritative owner**: `agent/project_intelligence/adapters/repo_index.py:ProjectIntelligenceRepoIndexService`
  (legacy `agent/atlas_repo_index_service.py:AtlasRepoIndexService` retired in PIR-15)
  (storage `agent/atlas_repo_index_storage.py:AtlasRepoIndexStorage`, schema
  `agent/atlas_repo_index_schema.py`, policies `agent/atlas_repo_index_policies.py`).
- **Known duplication**: file iteration also exists in
  `agent/project_intelligence/adapters/code_explorer.py:_iter_project_files` (legacy
  `agent/atlas_code_explorer.py` retired in PIR-15), in
  `ProjectIntelligenceCodeIntelAdapter` (legacy `AtlasCodeIntelService` retired in PIR-15),
  and in
  the Twin static analyzer (`agent/project_twin/static_graph.py`).
- **Reusable contracts**: repo-index schema; index-run JSON shape.
- **Missing behavior**: no revisioned node/edge graph identity, no provenance/confidence,
  no incremental invalidation (these exist only in the Twin).
- **Migration risk**: low — projection source; reads only.

### 4.2 Symbol & dependency extraction / call graph

- **Current capability**: deterministic Python symbol index (class/function/method/import
  via `ast`), import-dependency graph, related-test discovery.
- **Authoritative owner**: `agent/project_intelligence/adapters/code_intel.py`
  (`_PythonSymbolVisitor`, `ProjectIntelligenceCodeIntelAdapter.build_symbol_index`,
  `build_dependency_graph`, `find_related_tests`; schema `agent/atlas_code_intel_schema.py`;
  legacy `agent/atlas_code_intel_service.py:AtlasCodeIntelService` retired in PIR-15).
  Lighter heuristic variant: `agent/project_intelligence/adapters/code_explorer.py:extract_symbols`
  (legacy `agent/atlas_code_explorer.py` retired in PIR-15).
- **Known duplication**: symbol extraction + related-test discovery exist in **three**
  places: `agent/project_intelligence/adapters/code_intel.py`,
  `agent/project_intelligence/adapters/code_explorer.py`,
  and (test→impl)
  `atlas_test_impl_linker.py`; plus the Twin static graph.
- **Reusable contracts**: `AtlasSymbolIndexRequest`, `AtlasDependencyGraphRequest`,
  `AtlasRelatedTestsRequest` and their result models (pinned deterministic by baseline test).
- **Missing behavior** (ADR-PI-006): no resolved call edges (current calls are name-based
  `pyname://`), no inheritance/implementation resolution, no control-flow/data-flow,
  no JS/HTML semantic linking beyond regex heuristics.
- **Migration risk**: low — wrap behind Digital Twin semantic analyzer; do not modify.

### 4.3 Related-test discovery

- **Current capability**: maps implementation files/symbols to candidate tests.
- **Authoritative owner**: `agent/project_intelligence/adapters/code_explorer.py:find_related_tests`
  (legacy `agent/atlas_code_explorer.py` retired in PIR-15),
  `agent/project_intelligence/adapters/code_intel.py` related-tests, and
  `agent/atlas_test_impl_linker.py:find_implementation_item`.
- **Known duplication**: three related-test/impl-link mechanisms.
- **Reusable contracts**: `AtlasRelatedTestsRequest`.
- **Missing behavior**: not linked to requirements/runtime evidence or impact analysis.
- **Migration risk**: medium — used by verification recommendation; needs parity before cutover.

### 4.4 API route discovery

- **Current capability**: route/path heuristics in repo index service/policies; FastAPI
  registration via `app/server.py:include_routers()` and `main.py`.
- **Authoritative owner**: `agent/project_intelligence/adapters/repo_index.py` +
  `agent/atlas_repo_index_policies.py`; Twin route projection in
  `agent/project_twin/static_graph.py`.
- **Missing behavior**: no FastAPI route → handler → service → side-effect graph beyond
  the Twin's inferred projection.
- **Migration risk**: low.

### 4.5 Project & git inspection

- **Current capability**: inspects a project (structure/signals) and git state for the agent.
- **Authoritative owner**: `agent/atlas_project_inspection_service.py:AtlasProjectInspectionService`,
  `agent/atlas_git_inspection_service.py:AtlasGitInspectionService`.
- **Reusable contracts**: inspection result shapes.
- **Missing behavior**: not revisioned; not tied to twin lifecycle/mode detection.
- **Migration risk**: low — ADAPT into Digital Twin lifecycle/context.

### 4.6 Repository context construction / planner packaging

- **Current capability**: builds bounded prompt context, repo-context slices, and
  planner-facing context packages.
- **Authoritative owner**:
  - `agent/context_builder.py` (`ContextBuilder`, `TaskV2ContextBuilder`,
    `FileSummaryCache`, `ToolResultCache`, `_estimate_tokens`, `_truncate_to_token_budget`);
  - `agent/project_intelligence/adapters/repo_context_service.py:ProjectIntelligenceRepoContextService`
    (legacy `agent/atlas_repo_context_service.py:AtlasRepoContextService` retired in PIR-15)
    (schema `agent/atlas_repo_context_schema.py`);
  - `agent/project_intelligence/adapters/repo_context_packaging.py:ProjectIntelligenceRepoContextPackager`
    (legacy `agent/atlas_repo_context_planner_packager.py:AtlasRepoContextPlannerPackager`
    retired in PIR-15)
    (schema `agent/atlas_repo_context_planner_schema.py`);
  - `agent/project_intelligence/adapters/planner_packaging_v2.py:ProjectIntelligencePlannerPackagingV2Adapter`
    (legacy `agent/atlas_planner_packaging_v2_service.py:AtlasPlannerPackagingV2Service`
    retired in PIR-15)
    (schema `agent/atlas_planner_packaging_v2_schema.py`);
  - `agent/atlas_context_local_collectors.py` (aggregates code-intel + inspection).
- **Known duplication**: context assembly spread across ContextBuilder, RepoContext,
  ProjectIntelligenceRepoContextPackager, PlannerPackagingV2, and the Twin Context Broker
  (`agent/project_twin/context_broker.py`).
- **Reusable contracts**: repo-context + planner-packaging schemas; token estimation/truncation.
- **Missing behavior**: no single phase-aware `PlanningContextPackage`/`GenerationContextPackage`
  with Context Manifest, revision identity, and centralized inclusion/exclusion reasons
  (ADR-PI-012, ADR-PI-016).
- **Migration risk**: **medium-high** — these are on the active Planner path; reorganization
  must be additive, shadow-compared, and disable-safe.

### 4.7 Context refresh (v1 and v2)

- **Current capability**: refreshes/updates agent context between steps; v2 adds impact-aware
  refresh.
- **Authoritative owner**:
  `agent/project_intelligence/adapters/context_refresh_v1.py:ProjectIntelligenceContextRefreshAdapter`
  (legacy `agent/atlas_context_refresh_service.py:AtlasContextRefreshService` retired in
  PIR-15; schema/policies `atlas_context_refresh_schema.py`,
  `atlas_context_refresh_policies.py`),
  `agent/project_intelligence/adapters/context_refresh_v2.py:ProjectIntelligenceContextRefreshV2Adapter`
  (legacy `agent/atlas_context_refresh_v2_service.py:AtlasContextRefreshV2Service` retired in
  PIR-15; schema `atlas_context_refresh_v2_schema.py`).
- **Known duplication**: two refresh generations (v1, v2) coexist.
- **Missing behavior**: not revision-aware against a twin; no stale-context detection
  via Actual Twin revision.
- **Migration risk**: medium — multiple consumers (retry/handoff/autopilot APIs).

### 4.8 Impact map

- **Current capability**: maps a PlanItem to impacted files/tests.
- **Authoritative owner**:
  `agent/project_intelligence/adapters/plan_item_impact_map.py:ProjectIntelligencePlanItemImpactMapAdapter`
  (legacy `agent/atlas_plan_item_impact_map_service.py:AtlasPlanItemImpactMapService`
  retired in PIR-15); Twin impact in
  `agent/project_twin/analysis.py:GraphAnalysisService.assess_impact`.
- **Known duplication**: heuristic impact map vs. Twin graph impact.
- **Reusable contracts**: impact-map result shape; `ImpactRequest`/`ImpactResult` (twin).
- **Missing behavior**: heuristic map lacks resolved reverse-dependency/transitive analysis,
  recommended tests with provenance, and confidence (the Twin provides these but is not
  wired into production planning).
- **Migration risk**: medium.

### 4.9 Verification recommendation & gate (support, not authority)

- **Current capability**: recommends verification commands/tests; planning + handoff;
  truthful gate.
- **Authoritative owner**:
  - `agent/atlas_verification_recommendation_service.py:AtlasVerificationRecommendationService`
    (schema `atlas_verification_recommendation_schema.py`);
  - `agent/atlas_verification_recommendation_handoff_service.py:AtlasVerificationRecommendationHandoffService`
    (schema `atlas_verification_recommendation_handoff_schema.py`);
  - `agent/atlas_verification_planning_service.py`,
    `agent/atlas_verification_gate_service.py:AtlasVerificationGateService`
    (schema `atlas_verification_gate_schema.py`);
  - `agent/atlas_verification_resolver.py`, `agent/atlas_verification_allowlist.py`.
- **Authority note**: the verification **result and final safety gate are canonical**
  (KEEP). Recommendation services are *support* and may consume Digital Twin results.
- **Reusable contracts**: recommendation/gate schemas.
- **Missing behavior**: recommendations are not driven by resolved impact/test-selection
  from a deep graph.
- **Migration risk**: low-medium — ADAPT recommendation to consume Twin; never change the gate.

### 4.10 Requirement tracing (delivery trace)

- **Current capability**: traces requirements to files/items with status from explicit evidence.
- **Authoritative owner**: `agent/atlas_requirement_tracer.py:AtlasRequirementTracer`,
  `agent/requirement_analyzer.py`, `agent/requirement_schema.py`; Twin projection in
  `agent/project_twin/intent_trace.py`.
- **Authority note**: requirement source records are **canonical (KEEP)**; the Twin holds a
  delivery-trace projection.
- **Missing behavior**: full `Requirement → Blueprint Element → PlanItem → Proposal →
  Applied File/Symbol → Verification → Evidence` chain (master-goal completion rule) is not
  yet integrated end to end.
- **Migration risk**: low — KEEP canonical + ADAPT projection.

### 4.11 Runtime execution & normalization

- **Current capability**: pytest/Playwright/visual/Atlas Play execution; the Twin normalizes
  observations.
- **Authoritative owner (execution, KEEP)**: `agent/verification_runner.py`,
  `agent/atlas_playwright_smoke_verifier.py`, `agent/atlas_visual_artifact_verifier.py`,
  `app/atlas/play/`.
- **Normalization owner**: `agent/project_twin/runtime_collectors.py`
  (`PytestCollector`, `PlaywrightCollector`, `ApiObservationCollector`, `PlayConsoleCollector`,
  `RuntimeObservationIngestor`).
- **Missing behavior**: collectors are not wired to live runners in production; reconciliation
  (`agent/project_twin/reconciliation.py`) is not driven by real runs.
- **Truthfulness**: unavailable instrumentation must stay `unavailable`, never `passed`
  (ADR-PI-013) — already honored by the Twin collectors.
- **Migration risk**: medium — REPLACE scattered result shapes with the Twin runtime adapter.

### 4.12 Durable Memory

- **Current capability**: short-term ring buffer + pluggable long-term saver/searcher;
  durable item shapes.
- **Authoritative owner**: `agent/memory.py` (`MemoryStore`, `HybridMemoryStore`).
- **Adapter**: `agent/project_twin/memory_adapter.py` (verified-promotion gate).
- **Authority note**: KEEP canonical; ADAPT projection. Unverified inference must not
  become durable (pinned by baseline test: long-scope write without a saver is a no-op).
- **Migration risk**: low.

### 4.13 Skills

- **Current capability**: SKILL.md registry/resolver with safety precedence.
- **Authoritative owner**: `agent/project_twin/skill_registry.py`
  (`SkillRegistry`, `SkillResolver`).
- **Authority note**: KEEP definitions + safety precedence; a skill cannot expand
  execution authority (frozen safety invariant). ADAPT via Project Intelligence adapter.
- **Migration risk**: low.

### 4.14 Nexus external evidence

- **Current capability**: research/evidence store (SQLite), citation, reports.
- **Authoritative owner**: `app/nexus/` (`db.py`, `evidence.py`, `report.py`,
  `research_agent.py`, `schemas.py`, `router.py`); adapters
  `agent/atlas_nexus_research_adapter.py`, `agent/nexus_context_builder.py`,
  `agent/atlas_context_nexus_adapter.py`; Twin projection
  `agent/project_twin/nexus_adapter.py`.
- **Authority note**: KEEP canonical; external claims never become verified code truth.
- **Migration risk**: low.

### 4.15 Project Twin module (Core v1)

- **Current capability**: full Core v1 surface (see §2).
- **Authoritative owner**: `agent/project_twin/` package; public contracts re-exported by
  `agent/project_twin/__init__.py` (`atlas.project_twin.v1`); inspection API
  `app/api/project_twin.py`; UI `web/js/project_twin_panel.js`.
- **Reusable contracts**: `ProjectTwinPort`, `StaticAnalysisPort`, `TwinContextPort`,
  `RuntimeObservationPort`, `IntentTracePort`, `TwinMemoryPort`, `TwinSkillPort`,
  `TwinNode/Edge/Evidence/Revision/Delta`, query/trace/impact/context schemas.
- **Missing behavior**: no coarse `DigitalTwinModule` facade yet (PI-1); name-based calls
  and heuristic side effects are compatibility behavior (ADR-PI-006); not wired into
  production planning/generation/verification consumers (PI-16..PI-19).
- **Migration risk**: low for the facade (additive); the deep-graph upgrades (PI-6..PI-9)
  carry the real implementation risk.

## 5. Authoritative ownership map (summary)

| Domain source | Authoritative owner | PI relation |
|---|---|---|
| Code / workspace | Git + workspace; `ProjectIntelligenceRepoIndexService`, `ProjectIntelligenceCodeIntelAdapter` | projected into Digital Twin |
| Messages | `AtlasConversationStore` | referenced (delivery trace) |
| Requirements | `AtlasRequirementTracer` / requirement schema | KEEP canonical + ADAPT projection |
| Planning / execution | PlanPool/workflow stores | KEEP; referenced, never mutated |
| Approved target design | none yet | new Architecture Blueprint Module |
| Target-vs-actual gap | none yet | new Convergence Module |
| External evidence | Nexus (`app/nexus`) | KEEP + ADAPT |
| Durable memory | `HybridMemoryStore` | KEEP + ADAPT |
| Skills | `agent/project_twin/skill_registry.py` | KEEP + ADAPT |
| Runtime execution | verification runner / Playwright / visual / Play | KEEP |
| Runtime normalization | Twin runtime collectors | REPLACE scattered shapes |
| Revisioned interpretation | `agent/project_twin/` (Core v1) | DigitalTwinModule facade |

## 6. Known duplication / legacy paths (must consolidate, not delete prematurely)

1. **Symbol + related-test extraction** duplicated across
   `agent/project_intelligence/adapters/code_intel.py`,
   `agent/project_intelligence/adapters/code_explorer.py`,
   `atlas_test_impl_linker.py`,
   and `project_twin/static_graph.py`.
2. **File iteration** duplicated across repo index, code explorer, code intel, twin analyzer.
3. **Context assembly** duplicated across `context_builder.py`,
   `agent/project_intelligence/adapters/repo_context_service.py`,
   `agent/project_intelligence/adapters/repo_context_packaging.py`,
   `agent/project_intelligence/adapters/planner_packaging_v2.py`, and
   `project_twin/context_broker.py`.
4. **Context refresh** has two generations (`v1`, `v2`).
5. **Impact** has a Project Intelligence heuristic map
   (`agent/project_intelligence/adapters/plan_item_impact_map.py`) and a graph analyzer
   (`project_twin/analysis.py`).

Per ADR-PI-010 / migration plan §11–§18, none of these are deleted until consumer-zero +
parity + rollback + boundary-test gates pass.

## 7. Safety invariants confirmed unchanged by PI-0

PI-0 adds only documentation and a read-only baseline test. It does not touch workflow
state, PlanPool authority, clarification/critical-decision gates, profile/envelope/allowed
paths, Safe Apply, base revisions, rollback, bounded retry, command allowlists,
direct-merge/remote-push/self-apply restrictions, project/workspace isolation, truthful
verification, or the "unavailable is not passed" rule.

## 8. PI-0 acceptance check

- Authoritative owners identified (§4, §5).
- Duplication explicitly identified (§6).
- Direct consumers recorded by symbol — companion `consumer_map.md`.
- KEEP/ADAPT/REPLACE/REMOVE — companion `migration_matrix.md`.
- Baseline tests pin current public behavior — `tests/test_project_intelligence_baseline.py`.
- No production behavior changed.
- Old PDT status recorded as **Core v1 complete, not full program complete** (§2).
