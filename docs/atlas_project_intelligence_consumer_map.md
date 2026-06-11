# Atlas Project Intelligence — Consumer Map (PI-0)

> Generated for PI-0 against current `main` (HEAD `0fd98c1`).
> Records the **direct consumers** of each capability owner **by symbol**, so the
> reorganization packages (PI-16..PI-23) can migrate consumers in canonical order
> without leaving direct dependencies on legacy paths.
> Companion: `atlas_project_intelligence_existing_capability_map.md`,
> `atlas_project_intelligence_migration_matrix.md`.

## 1. Method

Consumers were located by symbol reference search across `agent/`, `app/`, and `main.py`,
excluding tests and the `.claude/worktrees/*` parallel checkouts (which are separate
working copies, not independent runtime consumers). A consumer is "direct" when it
imports and uses the owner symbol (construction or method call).

The canonical **target** consumer entrypoints (migration plan §5) — to which these
consumers must eventually move — are:

```text
Planner   -> ProjectIntelligenceModule.prepare_planning_context
Generator -> ProjectIntelligenceModule.prepare_generation_context
Safe Apply completion   -> ProjectIntelligenceModule.record_apply_result
Verification completion -> ProjectIntelligenceModule.record_verification_result
Inspection UI/API       -> ProjectIntelligenceModule / DigitalTwinModule public query
```

None of these target facades exist yet (PI-1). This map records the **current** wiring.

## 2. Consumer table (owner → direct consumers by symbol)

| Owner symbol | Direct consumers (symbol / file) | Consumer kind |
|---|---|---|
| `AtlasRepoIndexService` | `agent/atlas_repo_context_service.py:AtlasRepoContextService`; `app/api/atlas_code_intel.py`; `app/api/atlas_repo_index.py` | agent service + API |
| `AtlasCodeIntelService` | `agent/atlas_context_local_collectors.py`; `app/api/atlas_code_intel.py` | agent collector + API |
| `AtlasProjectInspectionService` | `agent/atlas_context_local_collectors.py`; `app/api/atlas_dev_tools.py` | agent collector + API |
| `AtlasGitInspectionService` | `agent/atlas_context_local_collectors.py`; `app/api/atlas_dev_tools.py` | agent collector + API |
| `agent/atlas_code_explorer.py:extract_symbols / find_related_tests / search_code_excerpts / build_research_evidence` | research/evidence + explorer callers (heuristic path) | helper functions |
| `agent/atlas_test_impl_linker.py:find_implementation_item` | verification recommendation / handoff path | helper function |
| `ProjectIntelligencePlanItemImpactMapAdapter` | `agent/project_intelligence/adapters/context_refresh_v2.py:ProjectIntelligenceContextRefreshV2Adapter`; `agent/project_intelligence/adapters/planner_packaging_v2.py:ProjectIntelligencePlannerPackagingV2Adapter`; `agent/project_intelligence/adapters/atlas_repo_context.py:AtlasRepoContextAdapter` | Project Intelligence adapter helper |
| `AtlasRepoContextService` | `agent/atlas_context_refresh_service.py:AtlasContextRefreshService`; `agent/project_intelligence/adapters/atlas_repo_context.py:AtlasRepoContextAdapter`; `agent/project_intelligence/adapters/repo_context_packaging.py:ProjectIntelligenceRepoContextPackager` | agent service + Project Intelligence adapters |
| `ProjectIntelligenceRepoContextPackager` | `agent/project_intelligence/adapters/atlas_repo_context.py`; `agent/project_intelligence/adapters/planner_packaging_v2.py`; `agent/project_intelligence/adapters/plan_item_impact_map.py` | Project Intelligence adapter helper |
| `AtlasContextRefreshService` | `agent/atlas_supervised_handoff_retry_service.py`; `agent/atlas_supervised_handoff_verification_service.py`; `app/api/atlas_bounded_retry.py`; `app/api/atlas_context_refresh.py`; `app/api/atlas_multi_item_autopilot.py`; `app/api/atlas_supervised_handoff_retry.py` | agent services + APIs |
| `ProjectIntelligenceContextRefreshV2Adapter` | `agent/project_intelligence/adapters/atlas_context_refresh.py`; `agent/project_intelligence/adapters/planner_packaging_v2.py`; `app/api/atlas_context_refresh.py` | Project Intelligence adapter helper + API |
| `ProjectIntelligencePlannerPackagingV2Adapter` | `agent/atlas_verification_recommendation_service.py:AtlasVerificationRecommendationService`; `app/api/atlas_pipeline.py`; `app/api/atlas_repo_context.py` | Project Intelligence adapter + API |
| `AtlasVerificationRecommendationService` | `agent/atlas_verification_recommendation_handoff_service.py:AtlasVerificationRecommendationHandoffService`; `app/api/atlas_pipeline.py`; `app/api/atlas_repo_context.py` | agent service + API |
| `AtlasVerificationRecommendationHandoffService` | `app/api/atlas_pipeline.py`; `app/api/atlas_repo_context.py` | API |
| `AtlasVerificationGateService` | `app/api/atlas_pipeline.py` | API |
| `agent/atlas_context_local_collectors.py` | `agent/atlas_context_refresh_service.py:AtlasContextRefreshService` | agent service |
| `agent/context_builder.py:ContextBuilder / TaskV2ContextBuilder` | `agent/loop.py` (agent execution loop) | agent loop |
| `agent/project_twin/` (Core v1 store + contracts) | `app/api/project_twin.py` (read-only inspection); `app/server.py` (router registration) | API only |

## 3. Key observations for migration sequencing

1. **`app/api/atlas_pipeline.py` and `app/api/atlas_repo_context.py` are the principal
   orchestration consumers.** They wire RepoContext → PlannerPackaging → Impact →
   VerificationRecommendation → Gate. These two API modules are the highest-value cutover
   targets for the future `ProjectIntelligenceModule.prepare_planning_context` /
   `prepare_generation_context` (PI-16..PI-18).

2. **`agent/atlas_context_refresh_service.py` is a hub**: it consumes RepoContext
   and the local collectors, and is itself consumed by the
   supervised-handoff/retry/autopilot APIs. Refresh is therefore on the critical context
   path and must be migrated with shadow comparison (PI-9 / PI-17).

3. **Context construction has layered consumers** (ContextBuilder -> loop; RepoContext ->
   ProjectIntelligenceRepoContextPackager -> PlannerPackagingV2 -> VerificationRecommendation). Cutover must be
   bottom-up: provide the new phase package, shadow-compare, then migrate the API
   orchestrators, then retire the intermediate packagers.

4. **The Digital Twin Core v1 has exactly one production consumer today**:
   `app/api/project_twin.py` (read-only inspection) plus router registration in
   `app/server.py`. **It is not yet consumed by any Planner/Generator/Verification path.**
   This is the central "production wiring gap" the program must close (PI-16..PI-19),
   and it means the Twin can be wrapped by `DigitalTwinModule` (PI-1) with negligible
   consumer-migration risk.

5. **`agent/loop.py` is the agent execution loop** and the eventual consumer of
   `GenerationContextPackage`. It currently uses `ContextBuilder` / `TaskV2ContextBuilder`
   directly.

6. **Verification authority is isolated from recommendation.** `AtlasVerificationGateService`
   (the truthful gate, canonical/KEEP) has a single API consumer and must never be made to
   depend on a projection. Recommendation/handoff/planning services are the ADAPT surface.

## 4. Consumer-zero gate (recorded for later packages)

Per migration plan §18, a legacy owner may be removed only when **all** of the consumers
listed in §2 for that owner have moved to the new facade/adapter, parity is measured,
rollback exists, and boundary tests reject reintroduction. PI-0 establishes this list as
the consumer-zero checklist; later packages update it as cutovers complete.
