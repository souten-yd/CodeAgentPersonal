# Atlas Project Intelligence — Migration Matrix (PI-0)

> Generated for PI-0 against current `main` (HEAD `0fd98c1`).
> This document **validates and expands** the initial matrix in
> `atlas_project_intelligence_migration_plan.md` §4 against current code, as PI-0 requires.
> Classification model (migration plan §2 / ADR-PI-010): `KEEP`, `ADAPT`, `REPLACE`, `REMOVE`.
> Companion: `atlas_project_intelligence_existing_capability_map.md`,
> `atlas_project_intelligence_consumer_map.md`.

## 1. Classification legend

- **KEEP** — canonical authority or specialized runtime stays in place; Project
  Intelligence receives events/result packages from it.
- **ADAPT** — existing implementation is retained but used behind a new module facade /
  compatibility adapter.
- **REPLACE** — a new module implementation becomes primary **after measured parity or
  documented superiority** in shadow mode.
- **REMOVE** — legacy implementation is deleted **only after all retirement gates pass**
  (consumer-zero + parity + rollback + boundary test; migration plan §18).

Every row records the **validated** owner symbol, the classification, the target module
owner, the PI destination package, and the retirement gate (where deletion is eventually
allowed).

## 2. Validated migration matrix

| # | Capability | Validated owner symbol(s) | Class | Target module owner | PI destination | Retirement gate |
|---|---|---|---|---|---|---|
| 1 | Repository enumeration | `AtlasRepoIndexService` (+ `_iter_project_files`, twin `static_graph`) | ADAPT → REPLACE | DigitalTwinModule | PI-1 facade, PI-6 deep graph, PI-23 cutover | consumer-zero on Repo Index after PI-23 |
| 2 | Symbol extraction | `AtlasCodeIntelService.build_symbol_index`; `atlas_code_explorer.extract_symbols`; twin `static_graph` | ADAPT → REPLACE | DigitalTwin semantic analyzer | PI-6, PI-23 | parity vs CodeIntel pinned by baseline test |
| 3 | Dependency/import graph | `AtlasCodeIntelService.build_dependency_graph`; twin `static_graph` | ADAPT → REPLACE | DigitalTwin semantic analyzer | PI-6, PI-23 | parity on edge set + scope |
| 4 | Resolved call / control-flow / data-flow graph | *(none — ADR-PI-006 gap)*; current `pyname://` name-based calls | REPLACE (net-new) | DigitalTwin deep graph | PI-6, PI-7 | real-repo benchmark (test plan §17) |
| 5 | Related-test discovery | `atlas_code_explorer.find_related_tests`; `AtlasCodeIntelService` related-tests; `atlas_test_impl_linker.find_implementation_item` | ADAPT → REPLACE | DigitalTwin impact/test selection | PI-9, PI-23 | parity vs all 3 legacy mechanisms |
| 6 | API route discovery | `AtlasRepoIndexService` + `atlas_repo_index_policies`; twin route projection | ADAPT → REPLACE | DigitalTwin API graph | PI-6 | route-set parity |
| 7 | Project inspection | `AtlasProjectInspectionService` | ADAPT | DigitalTwin lifecycle/context | PI-4 | n/a (ADAPT, no delete planned) |
| 8 | Git inspection | `AtlasGitInspectionService` | ADAPT | DigitalTwin lifecycle/context | PI-4 | n/a |
| 9 | Repository context | `AtlasRepoContextService`; `ContextBuilder`/`TaskV2ContextBuilder`; `ProjectIntelligenceRepoContextPackager` (legacy `AtlasRepoContextPlannerPackager` retired in PIR-15) | ADAPT → REPLACE | ProjectIntelligence context packages | PI-9, PI-16, PI-23, PIR-15 | shadow parity + consumer-zero + rollback proof |
| 10 | Planner packaging | `ProjectIntelligencePlannerPackagingV2Adapter` (legacy `AtlasPlannerPackagingV2Service` retired in PIR-15) | REPLACE | `PlanningContextPackage` | PI-16, PI-23, PIR-15 | shadow parity + consumer-zero + rollback proof |
| 11 | Context refresh | `AtlasContextRefreshService`; `ProjectIntelligenceContextRefreshV2Adapter` (legacy `AtlasContextRefreshV2Service` retired in PIR-15); `atlas_context_local_collectors` | ADAPT → REPLACE | ProjectIntelligence lifecycle/context | PI-9, PI-17, PI-23, PIR-15 | parity across handoff/retry/autopilot consumers + rollback proof |
| 12 | Impact map | `AtlasPlanItemImpactMapService`; twin `analysis.GraphAnalysisService.assess_impact` | ADAPT → REPLACE | DigitalTwin impact query + Atlas adapter | PI-9, PI-23 | impact precision/recall parity |
| 13 | Verification recommendation | `AtlasVerificationRecommendationService`; `AtlasVerificationRecommendationHandoffService`; `atlas_verification_planning_service` | ADAPT | Verification owner consuming DigitalTwin result | PI-19 | n/a (recommendation stays support) |
| 14 | Verification gate / result (authority) | `AtlasVerificationGateService`; `verification_runner`; `atlas_verification_resolver`; `atlas_verification_allowlist` | **KEEP** | Verification owner (canonical) | — | **never removed** (safety authority) |
| 15 | Requirement tracing | `AtlasRequirementTracer`; `requirement_analyzer`; twin `intent_trace` | KEEP canonical + ADAPT projection | Requirement owner + DigitalTwin delivery graph | PI-5, PI-15 | n/a for canonical |
| 16 | Runtime execution | `verification_runner`; `atlas_playwright_smoke_verifier`; `atlas_visual_artifact_verifier`; `app/atlas/play/` | **KEEP** | Verification/runtime owners | — | **never removed** |
| 17 | Runtime normalization | scattered result shapes; twin `runtime_collectors` | REPLACE | DigitalTwin runtime adapter | PI-8 | observation-shape parity; unavailable≠passed |
| 18 | Static/runtime reconciliation | twin `reconciliation.ReconciliationService` | ADAPT → REPLACE (deepen) | DigitalTwin runtime intelligence | PI-8 | reconciliation correctness on real runs |
| 19 | Memory | `HybridMemoryStore`; twin `memory_adapter` | KEEP + ADAPT | Memory owner + PI adapter | PI-5 | n/a (unverified inference stays non-durable) |
| 20 | Skills | twin `skill_registry.SkillRegistry/SkillResolver` | KEEP + ADAPT | Skill owner + PI adapter | PI-5 | n/a (cannot expand authority) |
| 21 | Nexus | `app/nexus/*`; `atlas_nexus_research_adapter`; twin `nexus_adapter` | KEEP + ADAPT | Nexus owner + PI adapter | PI-5 | n/a (external≠verified truth) |
| 22 | Project Twin Core v1 | `agent/project_twin/` package + `app/api/project_twin.py` | ADAPT (wrap) | DigitalTwinModule facade | PI-1 | n/a (facade is additive) |
| 23 | Architecture Blueprint | *(none — net-new)* | REPLACE (net-new) | ArchitectureBlueprintModule | PI-10..PI-12 | n/a |
| 24 | Convergence | *(none — net-new)* | REPLACE (net-new) | ConvergenceModule | PI-13..PI-15 | n/a |
| 25 | Greenfield generation | *(none — net-new on top of PlanPool/Safe Apply/Verification)* | REPLACE (net-new) | ProjectIntelligence orchestration | PI-20..PI-22 | n/a |

## 3. Deltas vs migration plan §4 (PI-0 validation result)

The initial matrix in the migration plan was validated against current main. Confirmed
accurate; the following were **expanded/clarified**:

- **Row 4 added**: resolved call / control-flow / data-flow graph is a *net-new REPLACE*
  capability (ADR-PI-006 gap), distinct from rows 2–3. The plan listed it implicitly under
  "symbol/dependency"; PI-0 separates it because it has no current owner.
- **Row 9 expanded**: `ContextBuilder`/`TaskV2ContextBuilder` (`agent/context_builder.py`)
  is a confirmed additional repository-context owner consumed by `agent/loop.py`; the plan
  named "Context Builder" generically.
- **Row 14 split out from row 13**: the verification **gate/result** is explicitly **KEEP**
  (safety authority) and is recorded separately from recommendation services (ADAPT), to
  prevent any future change that makes the gate depend on a projection.
- **Row 18 added**: static/runtime **reconciliation** (twin `reconciliation.py`) is called
  out separately from runtime normalization (row 17) because it is the correctness-critical
  part of ADR-PI-013 ("unavailable is never passed").
- **Rows 23–25 added**: Blueprint, Convergence, and Greenfield are net-new modules with no
  current owner; recorded here so the matrix is complete for the whole program, not only
  the legacy surface.

## 4. Cross-cutting migration rules (binding on all rows)

1. **Facade/adapter precedes cutover** (ADR-PI-010): no consumer is repointed until the
   target facade exists and a compatibility adapter wraps the legacy result.
2. **Shadow before authority** (migration plan §7): REPLACE rows run old + new from the
   same source revision and compare before the new path becomes primary.
3. **No new direct legacy dependency**: once a facade exists for a capability, new code
   must not add a fresh direct import of the legacy owner.
4. **No permanent duplication** (ADR-PI-010): the new module must not remain a parallel
   path; every REPLACE row ends in legacy retirement or a documented compatibility adapter.
5. **Authority never absorbed**: KEEP rows (14, 16, plus canonical sides of 15, 19, 20, 21)
   keep their authority; Project Intelligence consumes their events/results only.
6. **Unavailable is not passed** (ADR-PI-013): rows 17–18 must preserve explicit
   `unavailable` status; no completion may be synthesized from missing instrumentation.

## 5. PI-0 conclusion

The migration matrix is validated and complete for the program. Classifications are
recorded for every current owner symbol and every net-new module. No code is reclassified
into deletion at PI-0; all REMOVE outcomes are deferred to their retirement gates. This
matrix is the authoritative input to the cutover packages (PI-16..PI-23) and the
legacy-retirement gate (PI-25 / migration plan §18).
