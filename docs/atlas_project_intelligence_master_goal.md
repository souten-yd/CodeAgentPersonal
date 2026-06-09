# Atlas Project Intelligence — Master Goal

Status: canonical active goal.

PDT-0 through PDT-14 remain the completed Project Digital Twin Core v1. The active program completes production integration, deep graph intelligence, Architecture Blueprint, Convergence, Greenfield generation, and legacy consolidation.

## Mission

Build a portable Project Intelligence capability composed of four isolated modules:

1. Digital Twin Module — the actual project state.
2. Architecture Blueprint Module — the approved target state.
3. Convergence Module — target-versus-actual comparison and gap decisions.
4. Project Intelligence Module — orchestration and context delivery to Atlas.

The required flow is:

```text
Requirement
-> Blueprint
-> Planner / Plan Compiler
-> Proposal / Safe Apply / Verification
-> Actual Project Twin
-> Convergence
```

## Completion rule

A task is complete only when every mandatory requirement has evidence through:

```text
Requirement
-> Blueprint Element
-> PlanItem
-> Proposal
-> Applied File or Symbol
-> Verification
-> Runtime Observation or Evidence
```

Generated files, successful patch application, or a convergence score alone are not completion.

## Module boundary rule

Isolation is at module level, not per helper function. Each major module exposes one coarse-grained facade and may freely reorganize its internal analyzers, stores, and services.

Portable modules must not depend on Atlas workflow storage, FastAPI endpoints, UI DOM structures, or private PlanPool objects. Atlas integration is implemented through adapters outside the portable cores.

## Digital Twin capability target

The Digital Twin Module must contain real implementations for:

- structural and semantic graphs;
- resolved call graph;
- control-flow and data-flow graphs;
- state, event, recovery, and side-effect graphs;
- API, schema, database, file, network, process, configuration, dependency, UI, and rendering relations;
- runtime trace and static/runtime reconciliation;
- requirement, delivery, and evidence trace;
- path, impact, and test-selection analysis.

The current name-based calls and heuristic side-effect classification are compatibility behavior, not the final capability.

## Existing-project goal

Atlas must build or refresh the Actual Twin, create a scoped Change Blueprint, compile unresolved gaps into PlanPool, implement them, ingest verification, and decide between continue, local repair, downstream replan, Blueprint revision, critical decision, safe halt, or completion.

## Greenfield goal

For an empty project Atlas must create a reviewed Blueprint with an exact file manifest, interfaces, data models, dependencies, entrypoints, build/start commands, runtime scenarios, and verification contracts before broad generation. It then generates dependency-ordered slices, refreshes the Actual Twin after each slice, and proves convergence with build and runtime evidence.

## Existing feature consolidation

Overlapping repository scanning, symbol extraction, related-test discovery, context construction, impact mapping, verification recommendation, requirement tracing, and runtime normalization must be classified as KEEP, ADAPT, REPLACE, or REMOVE. Legacy code is removed only after consumers migrate, parity is measured, rollback exists, and affected tests pass.

## Authority invariants

Requirement remains authoritative for intent; Blueprint for approved target design; Workspace/Git for code; PlanPool for execution state; Safe Apply for mutation; Verification/runtime systems for observed behavior; Nexus for external research; and Memory for durable knowledge. Digital Twin and Convergence never become execution authorities.

## Final Definition of Done

The program is complete only when the four facades are used by production Atlas paths, deep graph capabilities pass real-repository benchmarks, Blueprint and Actual facts cannot be confused, Convergence drives bounded recovery decisions, empty-project E2E scenarios build and run, duplicate legacy paths are consolidated, cross-platform results are recorded truthfully, and safety boundaries remain unchanged.
