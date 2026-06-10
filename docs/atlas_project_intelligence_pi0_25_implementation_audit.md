# Atlas Project Intelligence — PI-0..PI-25 Implementation Audit

Status: canonical corrective audit for the Project Intelligence program.

Audit target: current `main` after the merge of PI-25.

## 1. Executive conclusion

PI-0 through PI-25 produced a substantial contract, model, helper, persistence, and unit-test foundation. They did **not** produce the production Project Intelligence loop required by the master goal.

The accurate status is:

```text
FRAMEWORK / COMPONENT FOUNDATION COMPLETE
PRODUCTION PROJECT-INTELLIGENCE LOOP NOT CONNECTED
REAL-ENVIRONMENT DEFINITION OF DONE NOT SATISFIED
```

Do not treat the merged package count or the number of focused tests as proof that the overall program is implementation-complete.

Current estimated completion by layer:

| Layer | Estimated completion |
|---|---:|
| Architecture decisions and public contracts | 85-90% |
| Independent helper/components | 65-75% |
| Durable module implementations | 30-40% |
| Atlas production wiring | 10-15% |
| Real existing-project convergence loop | 5-10% |
| Real Greenfield generation/build/run loop | 5-10% |
| Live rollout, cross-platform evidence, benchmark, retirement | 0-10% |
| Overall master goal | approximately 35-40% |

## 2. Audit method

Each work package was checked against four distinct completion levels:

1. **Contract present** — DTOs, protocols, schemas, or documented decisions exist.
2. **Component implemented** — isolated logic exists and has focused tests.
3. **Production connected** — the real Atlas API/planner/proposal/apply/verification path invokes it.
4. **Operationally proven** — real repositories, real commands, restart, cross-platform, and failure recovery have evidence.

A package is not complete merely because levels 1-2 exist.

## 3. Cross-program critical findings

### C-01 — Production composition always defaults to disabled modules

`agent/project_intelligence/factory.py` constructs disabled Twin, Blueprint, and Convergence modules unless a caller manually injects alternatives. No production application composition root supplies concrete modules.

### C-02 — Coordinator active mode discards module output

`ProjectIntelligenceCoordinator.prepare_planning_context` and `prepare_generation_context` call the Twin facade in active mode, but discard the returned context and return baseline packages. `record_apply_result` and `record_verification_result` return `accepted=False`; `evaluate_progress` always returns `complete=False`.

### C-03 — New Atlas adapters are not connected to real Atlas consumers

The Project Intelligence planner, generator, and verification adapters exist under `agent/project_intelligence/adapters/`, but the real Atlas API still constructs the legacy Planner, Repo Context, Impact Map, Verification Recommendation, Proposal, and Verification services.

### C-04 — No concrete Digital Twin module implementation

`DigitalTwinModule` is a protocol and `DisabledDigitalTwinModule` is implemented. The analyzers, graphs, lifecycle decisions, event bridge, runtime helpers, and context builders remain independent utilities. No concrete facade owns and coordinates source snapshot acquisition, analysis, revision creation, graph persistence, event/runtime ingestion, query/context construction, and readiness.

### C-05 — No concrete Convergence module implementation

Matcher, evaluator, policy, completion, and store helpers exist, but the public facade only has `DisabledConvergenceModule`.

### C-06 — “Real E2E” and final benchmark are synthetic

The Greenfield E2E tests use injected pass/fail/unavailable runners. Project files are dictionaries rather than a generated workspace. The final benchmark supplies hand-authored metric values rather than running both Atlas paths.

### C-07 — No independent CI evidence on the audited merge

No associated GitHub Actions workflow runs or status checks were present for the audited merge.

## 4. Detailed work-package audit

Status labels:

```text
ACCEPTABLE FOUNDATION
PARTIAL
SCAFFOLD ONLY
INCORRECT COMPLETION CLAIM
REQUIRES REWORK
```

### PI-0 — Production baseline and consumer map

**Audit status: PARTIAL**

Implemented: documentation inventory and baseline tests.

Missing:

- no executable consumer inventory generated from the current import/call graph;
- no runtime proof identifying which production consumer uses which facade;
- no machine-checkable zero-consumer retirement evidence;
- maps were not refreshed after PI-25.

Required correction: generate a current consumer registry from AST/import discovery plus runtime telemetry; record legacy and facade call counts per phase; make it a CI artifact and rollout gate.

### PI-1 — Module facade contracts and boundary tests

**Audit status: ACCEPTABLE FOUNDATION, incomplete implementation**

Implemented: versioned DTOs, protocols, disabled fail-closed facades, boundary tests.

Missing:

- no concrete `DigitalTwinModule`;
- no concrete `ConvergenceModule`;
- composition dependencies are typed as disabled implementations rather than public protocols;
- no reusable conformance suite for every concrete facade.

Required correction: type all dependencies as protocols, implement concrete facades, and add facade conformance tests.

### PI-2 — Persistence and migration foundation

**Audit status: PARTIAL; durability defects**

Implemented: isolated SQLite artifact stores, immutable revisions, idempotency primitives, migrations.

Defects and gaps:

1. Stores default to `:memory:` and production paths do not supply durable DB locations.
2. Blueprint lifecycle status is stored in an in-memory `_status` dictionary and can be lost on restart.
3. Delivery trace projection is in memory.
4. Semantic and behavioral graphs are not persisted through a concrete Twin module.
5. Checkpoint persistence defaults to `:memory:` and is not wired to the Atlas data root.
6. No real process-restart migration test uses the production path.
7. No atomic boundary ties graph revision, facts, context manifest, and head advancement.

Required correction: production storage configuration, durable lifecycle state, durable event projection, revisioned graph persistence, and restart/corruption/backup tests.

### PI-3 — Composition root and rollout model

**Audit status: SCAFFOLD ONLY**

Implemented: rollout config, telemetry sink, disabled coordinator/factory.

Missing:

- production service composition;
- durable telemetry;
- active package construction from real module output;
- rollout preflight proving concrete module health;
- per-workspace service lifecycle.

Required correction: implement `build_production_project_intelligence`, construct durable modules from `ca_data_dir`, register on app state, and fail closed when active dependencies are unavailable.

### PI-4 — Project identity, mode detection, lifecycle

**Audit status: PARTIAL**

Implemented: identity/mode/readiness/job decision helpers.

Missing:

- source snapshot service;
- real Git/worktree revision resolution in production;
- persistent last-build record;
- real full/incremental refresh worker;
- application open/close hooks;
- production symlink/path-escape evidence.

### PI-5 — Canonical event bridge and delivery trace

**Audit status: PARTIAL; correctness defects**

Implemented: event envelope, event mappings, in-memory projector, retry request.

Defects and gaps:

1. Canonical Atlas operations do not emit into the bridge in production.
2. Projector state is keyed by project only, not `(project_id, workspace_id)`.
3. Retry jobs do not retain a durable event payload or guaranteed lookup reference.
4. Idempotency and projection state are lost on restart.
5. Declared Memory/Skill/Nexus event families are ignored.
6. Project/workspace lifecycle events do not trigger a real Twin action.

### PI-6 — Static and semantic graph v2

**Audit status: PARTIAL; not the required deep semantic graph**

Implemented: deterministic refs, Python AST extraction, imports/aliases/re-exports/inheritance/decorators, resolved/candidate calls, basic JS/TS/Vue extraction, file invalidation.

Defects and limitations:

1. Analysis is primarily file-local; there is no whole-project linker.
2. Imported targets may be marked resolved without proving the target exists.
3. Override and dispatch resolution covers only simple cases.
4. No type/receiver flow, Protocol resolution, framework DI, route/schema linking.
5. TS/Vue parsing is regex-based.
6. LSP is not an operating enrichment broker.
7. Normal analysis returns an empty parity field.
8. The graph is not persisted or used through a concrete Twin module.

### PI-7 — Behavioral graph v2

**Audit status: REQUIRES REWORK for the master-goal capability**

Implemented: route, side-effect, state, recovery, UI-event, and API-call facts plus a reachability helper.

Defects:

1. “Control flow” is a count summary, not a basic-block CFG.
2. No def-use, alias, value, taint, return, argument, or interprocedural data flow.
3. State transitions are not represented; only assignments are detected.
4. Event/retry/rollback transitions are shallow heuristics.
5. Every UI event may be linked to every API call in the same file.
6. Side effects use call-name/string heuristics and inconsistent resource identities.
7. No semantic receiver integration or production persistence.

### PI-8 — Runtime intelligence and reconciliation v2

**Audit status: PARTIAL**

Implemented: pytest/Playwright/API normalizers, unavailable handling, reconciliation and rollup helpers.

Defects and gaps:

1. Normalizers are not wired to real verification outputs.
2. Coverage is flattened and attached to every test, which can overstate per-test coverage.
3. Stack-frame mapping assumes file/function pairs directly match canonical symbols.
4. No integrated process/file/DB/network/UI/state-transition collectors.
5. No durable observation store or production reconciliation.
6. Source revision and Twin revision semantics are not consistently separated.

### PI-9 — Context, path, impact, and test selection v2

**Audit status: PARTIAL**

Implemented: reverse-call impact, path query, coverage-based test recommendation, bounded context package.

Defects:

1. Context expansion is mostly one-hop call edges.
2. Objective and phase are not materially used in ranking.
3. Source material always takes the first 25 lines rather than symbol ranges.
4. Essential items may exceed budget without a defined overflow contract.
5. Test selection inherits the coverage defect.
6. No production consumer uses the package.

### PI-10 — Blueprint model, store, and lifecycle

**Audit status: PARTIAL; restart defect**

Implemented: immutable payloads, lifecycle concepts, active pointer, planned/Actual guard.

Defects:

1. Lifecycle status is not durable.
2. Generic `get_active` returns `None`.
3. Create produces a nearly empty Blueprint and does not invoke the PI-11 generator.
4. Review/approval state and review artifacts are not persisted.
5. No optimistic-lock protection for review/activation races.
6. Not connected to the coordinator.

### PI-11 — Blueprint generation, review, and validation

**Audit status: PARTIAL**

Implemented: `BlueprintSpec` conversion and basic manifest/execution/coverage/cycle validation.

Defects and gaps:

1. No production Planner/LLM adapter creates the spec from requirements and Actual context.
2. Stack, data models, API schemas, configuration, NFRs, error/recovery, and runtime scenarios are not first-class structures.
3. Scope selection can choose full-project from file count alone.
4. Execution contracts are checked for type presence, not usable command values.
5. No review persistence or critical-decision integration.

### PI-12 — Blueprint-to-Actual mapping hints

**Audit status: ACCEPTABLE FOUNDATION, not operational**

Implemented: exact/inferred/evidence-gated mapping helpers.

Missing: concrete Convergence integration, durable mapping history, rename/move/signature matching, ambiguity workflow, and quality benchmark.

### PI-13 — Convergence matcher and evaluator

**Audit status: PARTIAL; revision correctness defect**

Implemented: element states, basic structural/interface/verification evaluation, immutable report DTO.

Defects:

1. Verification `source_revision` is compared to `twin_revision_id`, although these are distinct identities.
2. Interface comparison is only a coarse kind check.
3. No API/schema/signature/data/config/dependency/behavior/state/side-effect/NFR comparison.
4. Mandatory elements with unavailable evidence can remain materialized without becoming mandatory gaps.
5. No concrete module persists or exposes reports.
6. Incremental reuse does not fully prove prior evidence remains valid.

### PI-14 — Convergence decision and incremental reevaluation

**Audit status: PARTIAL; unsafe completion logic**

Implemented: deterministic bounded actions and downstream calculation.

Defect: `complete` can be returned when there are no mandatory gaps and any element is verified. This does not prove every mandatory element satisfies its evidence policy.

Other gaps: Blueprint element IDs are assumed to equal PlanItem IDs; no persisted decision; no real continuation/replanning/critical-decision integration.

### PI-15 — Completion and requirement-evidence integration

**Audit status: ACCEPTABLE FOUNDATION, not connected**

Implemented: stronger all-gates completion evaluator.

Missing: real final-rollup integration, durable delivery trace queries, all-mandatory-element policy, internal provenance/freshness checks, and persisted completion report.

### PI-16 — Planning envelope and Plan Compiler

**Audit status: PARTIAL; compiler defects**

Implemented: deterministic per-element specs, revision references, completed/preserved statuses.

Defects:

1. Dependency cycles are silently ignored rather than rejected.
2. One item is created per element instead of coherent implementation slices.
3. Pseudo-elements can become file items with empty targets.
4. It does not create the real authoritative `AtlasPlanPool`.
5. No planning-envelope hash is computed.
6. Input revisions and target/requirement/criteria executability are not validated.
7. Existing authoritative PlanItem state is not truly preserved during replan.

### PI-17 — Planner production integration

**Audit status: SCAFFOLD ONLY; completion claim incorrect**

Implemented: isolated off/shadow/active context adapter.

Missing/incorrect:

- real Atlas Planner does not invoke it;
- tests use the disabled factory;
- active mode succeeds with disabled readiness and baseline content;
- no stale refresh/blocking policy;
- no real PlanPool manifest/revision persistence.

### PI-18 — Generator and repair production integration

**Audit status: SCAFFOLD ONLY; completion claim incorrect**

Implemented: generation context adapter, stale check, planned/Actual labels, repair-action validation.

Missing:

- no `AtlasPatchProposalService` integration;
- no real proposal metadata persistence;
- no concrete revision source;
- no safe source materializer;
- no evidence-driven self-correction/replan integration.

### PI-19 — Verification, checkpoint, and resume

**Audit status: PARTIAL SCAFFOLD**

Implemented: checkpoint DTO/store helper, idempotency, external-change decision, rollup adapter.

Defects:

1. Real verification does not invoke it.
2. Default DB is in memory.
3. It does not actually ingest into Twin or evaluate Convergence.
4. PlanPool revision may be used as a source rollback revision.
5. No coordinated apply idempotency.
6. No continuation/recovery service integration.

### PI-20 — Greenfield bootstrap orchestrator

**Audit status: PARTIAL SCAFFOLD**

Implemented: mode/Blueprint gates, dependency layers, serializable session, no direct mutation.

Missing: Atlas entrypoint, Proposal, Safe Apply, Actual refresh, Convergence, durable session store. `complete_slice` trusts a Boolean rather than a typed canonical Safe Apply result.

### PI-21 — Coherent multi-file generation

**Audit status: PARTIAL**

Implemented: static consistency checks.

Missing: production invocation, parser-backed checks, robust API agreement, build/dependency integration, and typed repair packages connected to the real loop.

### PI-22 — Greenfield build/run/test and real E2E

**Audit status: INCORRECT COMPLETION CLAIM**

Implemented: profile detection, command selection, runner abstraction, synthetic harness.

Defects:

1. Commands are not executed in tests; runners return predetermined results.
2. No workspace is generated.
3. The normal Atlas requirement/API/PlanPool path is not used.
4. Persistence checks use placeholder Python command strings.
5. Profile commands are too coarse for arbitrary projects.
6. Start success is only return code zero, not readiness/health/browser behavior.
7. Six profiles exist despite comments referring to eight scenarios.

### PI-23 — Capability consolidation and consumer cutover

**Audit status: SCAFFOLD ONLY**

Implemented: in-memory registry, comparison helper, conceptual cutover order/gate.

Missing: real consumer discovery/population, production migration, durable parity evidence, import lint, zero-consumer proof, and production rollback exercise.

### PI-24 — Cross-platform, scale, storage, and rollout hardening

**Audit status: SCAFFOLD ONLY for operational evidence**

Implemented: platform detection, arithmetic budgets, retention/export/import/coalescing helpers, in-memory rollout gate.

Missing: real Windows/Linux/Docker/Runpod runs, large-repo benchmark, concurrency/load evidence, durable rollout state, telemetry-driven rollback, and real disk/compaction testing.

### PI-25 — Final benchmark and legacy retirement

**Audit status: INCORRECT COMPLETION CLAIM**

Implemented: metric calculator, Boolean DoD evaluator, retirement-condition helper.

Missing:

1. No real legacy/final executions.
2. No representative corpus or repeated trials.
3. No cost/failure taxonomy collection.
4. No zero-consumer production state.
5. No legacy retirement.
6. Live gates remain pending.

## 5. Corrected completion classification

| WP range | Correct classification |
|---|---|
| PI-0..PI-2 | foundation; durability fixes required |
| PI-3..PI-5 | orchestration/event scaffolding; not production connected |
| PI-6..PI-9 | prototype graph/query implementation; deep capabilities incomplete |
| PI-10..PI-12 | Blueprint foundation; lifecycle/generation integration incomplete |
| PI-13..PI-15 | Convergence/completion algorithms; concrete module and correctness fixes required |
| PI-16 | Plan compiler prototype; not PlanPool production integration |
| PI-17..PI-19 | adapter scaffolds; not production integrations |
| PI-20..PI-22 | Greenfield prototypes; no real E2E |
| PI-23..PI-25 | rollout/benchmark gate helpers; no live cutover or benchmark |

## 6. Required program reset

The existing PI-0..PI-25 history remains valuable and must not be deleted or restarted wholesale. It becomes the **Foundation Track**.

The active corrective track is `PIR-0` through `PIR-15`, defined in:

- `docs/atlas_project_intelligence_recovery_master_goal.md`
- `docs/atlas_project_intelligence_recovery_detailed_design.md`
- `docs/atlas_project_intelligence_recovery_implementation_plan.md`
- `docs/atlas_project_intelligence_recovery_test_plan.md`
- `docs/atlas_project_intelligence_recovery_current_status.md`
- `docs/atlas_project_intelligence_recovery_agent_entrypoint.md`

Do not mark the overall Project Intelligence program complete until `PIR-15` and all live Definition of Done gates pass.
