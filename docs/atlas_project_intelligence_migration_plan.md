# Atlas Project Intelligence — Existing Feature Reorganization and Migration Plan

Status: canonical migration design.

## 1. Purpose

The new Project Intelligence architecture must not remain as an additional parallel path beside existing repository analysis, context, impact, and verification logic. Existing capabilities are progressively reorganized behind module facades, compared in shadow mode, migrated consumer by consumer, and retired only with evidence.

This document defines migration decisions and prohibits premature deletion or permanent duplication.

## 2. Classification model

Every existing capability receives one classification:

- `KEEP`: canonical authority or specialized runtime remains in place.
- `ADAPT`: existing implementation is used behind a new module facade.
- `REPLACE`: new implementation becomes primary after measured parity or superiority.
- `REMOVE`: legacy implementation is deleted after all retirement gates pass.

Classification applies to capabilities and consumers, not merely filenames. A file can contain more than one classification.

## 3. Authority-preserving KEEP areas

The following remain canonical and are not absorbed by Project Intelligence:

- Requirement source records and user decisions;
- Conversation storage;
- PlanPool and workflow state;
- proposal approval state;
- Safe Apply, allowed paths, and base revisions;
- rollback and bounded retry;
- command allowlists and execution authority;
- canonical verification result and final safety gate;
- Nexus documents/evidence;
- durable Memory storage;
- Skills definitions and safety precedence;
- Atlas Play session/process authority.

Project Intelligence receives canonical events or public result packages from these owners.

## 4. Initial migration matrix

PI-0 must validate and expand this matrix against current main.

| Capability | Current candidates | Initial class | Target owner |
|---|---|---|---|
| Repository enumeration | Repo Index, Code Intel, Code Explorer, Twin static analyzer | ADAPT then REPLACE | Digital Twin Module |
| Symbol extraction | Code Intel, Code Explorer, Twin static graph | ADAPT then REPLACE | Digital Twin semantic analyzer |
| Dependency/import graph | Code Intel, Twin static graph | ADAPT then REPLACE | Digital Twin semantic analyzer |
| Related-test discovery | Code Intel, Code Explorer, Test Impl Linker | ADAPT then REPLACE | Digital Twin impact/test selection |
| API route discovery | Repo Index policies, Twin static graph | ADAPT then REPLACE | Digital Twin API graph |
| Project inspection | Project Inspection, Git Inspection | ADAPT | Digital Twin lifecycle/context |
| Repository context | Repo Context, Context Builder, Planner Packager | ADAPT then REPLACE | Project Intelligence context packages |
| Context refresh | Context Refresh v1/v2 | ADAPT then REPLACE | Project Intelligence lifecycle/context |
| Impact map | Plan Item Impact Map, Twin impact | ADAPT then REPLACE | Digital Twin impact query + Atlas adapter |
| Verification recommendation | Verification Recommendation services | ADAPT | Verification owner consuming Digital Twin result |
| Requirement tracing | Requirement Tracer, PlanPool maps, Twin intent trace | KEEP canonical + ADAPT projections | Requirement/Verification + Twin delivery graph |
| Runtime execution | Verification Runner, Playwright, Visual verifier, Atlas Play | KEEP | Verification/runtime owners |
| Runtime normalization | scattered result shapes, Twin collectors | REPLACE | Digital Twin runtime adapter |
| Memory | HybridMemoryStore and Twin adapter | KEEP + ADAPT | Memory owner + Project Intelligence adapter |
| Skills | Skill registry/resolver | KEEP + ADAPT | Skill owner + Project Intelligence adapter |
| Nexus | Nexus DB/services and Atlas adapters | KEEP + ADAPT | Nexus owner + Project Intelligence adapter |

## 5. Target consumer model

After migration, production consumers use the following entrypoints:

```text
Planner
  -> ProjectIntelligenceModule.prepare_planning_context

Patch Generator / Repair
  -> ProjectIntelligenceModule.prepare_generation_context

Safe Apply completion
  -> ProjectIntelligenceModule.record_apply_result

Verification completion
  -> ProjectIntelligenceModule.record_verification_result

Inspection UI/API
  -> ProjectIntelligenceModule / DigitalTwinModule public query
```

Consumers must not call legacy analysis/context services directly after their cutover package.

## 6. Compatibility adapter design

Compatibility adapters live inside or adjacent to the owning module and translate existing results into public module contracts.

Examples:

```text
LegacyCodeIntelAdapter
LegacyRepoIndexAdapter
LegacyRepoContextAdapter
LegacyImpactMapAdapter
LegacyVerificationRecommendationAdapter
LegacyRequirementTraceAdapter
```

Rules:

- adapters may import legacy public services;
- portable module cores must not import Atlas workflow or API code;
- adapter output includes provenance and legacy version;
- adapter failures are explicit diagnostics;
- no adapter may mutate canonical workflow state;
- new code must not add fresh direct dependencies on legacy services.

## 7. Shadow comparison

Before authority cutover, old and new results execute from the same source revision and input.

Comparison dimensions:

### Project analysis

- enumerated files;
- symbols and locations;
- imports/dependencies;
- routes;
- related tests;
- changed and impacted files.

### Context

- included files/symbols;
- requirement and preserve-behavior coverage;
- context tokens;
- stale/incorrect facts;
- planner/generator outcome.

### Impact and verification

- directly and transitively impacted refs;
- recommended tests;
- false positives and false negatives;
- verification result and regression detection.

Every difference is classified as:

```text
expected_new_capability
legacy_false_positive
legacy_false_negative
new_false_positive
new_false_negative
representation_only
unknown_requires_review
```

## 8. Cutover order

Migrate in increasing order of authority/risk:

1. read-only health and inspection;
2. diagnostic UI/API;
3. Planner shadow context;
4. Planner active context;
5. Generator shadow context;
6. Generator active context;
7. impact mapping;
8. verification recommendation;
9. repair context;
10. final-rollup support;
11. legacy retirement.

No cutover step automatically enables the next step.

## 9. Per-consumer cutover procedure

For each consumer:

1. locate all direct legacy calls;
2. add facade dependency injection;
3. add off/shadow/active behavior;
4. preserve legacy result as fallback;
5. store comparison telemetry in shadow;
6. run focused and affected tests;
7. run representative real task;
8. set new path primary only after acceptance;
9. track remaining direct legacy calls;
10. update migration matrix and current status.

## 10. Legacy retirement gates

A legacy capability may be removed only when all gates pass:

- consumer search finds zero production direct callers;
- compatibility adapter is unused or intentionally retained;
- shadow parity or documented superiority exists;
- focused and affected tests pass;
- real E2E scenarios pass;
- rollback/recovery procedure exists;
- canonical data is not lost;
- Windows/Linux implications are checked;
- architecture-boundary test prevents reintroduction;
- documentation and current status are updated.

Removal is its own reviewable change. Do not combine high-risk consumer cutover and broad deletion in one PR.

## 11. Data migration policy

Canonical Atlas JSON stores are not migrated into Project Intelligence persistence.

Project Intelligence stores projections and references. Rebuildable Twin data may be discarded and rebuilt after explicit integrity failure. Blueprint and Convergence revisions are durable module artifacts and require migration/backup discipline.

Rules:

- no destructive migration without explicit backup and rollback;
- old Project Twin v1 store remains readable during migration;
- projection version changes may trigger rebuild rather than unsafe in-place reinterpretation;
- Blueprint revision identities never silently change;
- Convergence reports retain referenced Blueprint/Twin revision IDs.

## 12. Rollback policy

Each cutover must support immediate rollback through rollout configuration.

Rollback result:

- legacy consumer path restored;
- new module data retained for diagnosis unless corrupt;
- no canonical result is rewritten;
- comparison/incident diagnostics recorded;
- rollback does not imply deleting new module data.

## 13. Reorganization anti-patterns

Do not:

- copy old services into new packages without eliminating ownership ambiguity;
- keep both paths permanently active without a retirement decision;
- rewrite all existing analysis in one package;
- delete legacy code based only on unit-test parity;
- change canonical authority while moving code;
- expose many micro-ports solely to mirror old functions;
- make Digital Twin depend on PlanPool internals;
- make Planner know graph storage schema.

## 14. Completion condition

Reorganization is complete when:

- Project Intelligence facades are the production entrypoints;
- project-analysis duplication has a single owning module;
- legacy context/impact paths have zero direct production consumers or an explicitly documented retained role;
- canonical authority boundaries remain intact;
- architecture-boundary and retirement tests prevent regression;
- final benchmark uses the consolidated path.
