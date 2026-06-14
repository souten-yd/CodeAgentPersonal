# Atlas Project Intelligence Behavioral Impact Hardening Plan

## Purpose

This plan defines the next Atlas development track after the completed Project Intelligence Recovery, Portal, Play, Capsule, and Model Forge foundation work.

The goal is to turn the existing Project Digital Twin / Project Intelligence foundations into a practical planning and change-impact system:

```text
When Atlas plans or proposes a change, it should know:
- which functions, variables, states, resources, UI paths, APIs, tests, and historical incidents are related;
- what can break if a target file/function/state is modified;
- which tests and runtime checks should be run;
- when web research should augment planning;
- how slow local models can complete planning without false stall timeouts.
```

This is a hardening and completion track. Do not restart Project Intelligence, Digital Twin, Portal, Play, Capsule, Forge, PlanPool, Proposal, Safe Apply, Verification, or Convergence from scratch.

## Track Name

Atlas Project Intelligence Behavioral Impact Hardening, abbreviated as `PIBIH`.

## Non-negotiable Safety Boundaries

- Project Intelligence is advisory context and evidence. It is not execution authority.
- Atlas remains the authority for requirement, PlanPool, Proposal, Safe Apply, Verification, Repair, and Convergence.
- Portal owns runtime execution, artifact lifecycle, generated-data save/discard, and Capsule replay.
- Forge owns model/provider/profile routing and benchmark evidence.
- Nexus owns external web research. External/web calls remain policy-gated and disabled by default.
- `unavailable` is not `passed`.
- Inferred graph facts are not verified facts.
- Mock results are not live evidence.
- UI rendering is not runtime evidence.
- No code path may bypass Proposal / Safe Apply / Verification.
- No external provider may run in Local Only mode.
- Secrets must never be persisted, logged, returned by API, embedded in Capsule ZIPs, or included in Project Intelligence stores.
- Implementation size alone is not a stop condition.

## Current Baseline Assessment

The existing codebase already has important foundations:

- `agent/project_twin/contracts.py` defines graph contracts, query contracts, `ImpactRequest`, `ImpactResult`, `PathTraceRequest`, and context slices.
- `agent/project_twin/store.py` implements a durable SQLite-backed Twin Store with revisioning, idempotent deltas, scope isolation, invalidation, snapshots, and queries.
- `agent/project_twin/static_graph.py` projects structural nodes and edges for repository/file/module/class/function/method/import/inheritance/calls/FastAPI routes/tests/fixtures/HTML/JS assets.
- `agent/project_twin/behavioral_graph.py` already infers behavioral nodes and edges for side effects, UI interactions, CFG, SSA-lite, state/recovery, resource identity, and data-flow/side-effect relations, but it remains heuristic and needs deeper accuracy and stronger downstream use.
- `agent/project_intelligence/rollout.py` keeps Project Intelligence off by default and gates active/shadow behavior by phase.
- `agent/project_intelligence/coordinator.py` can use the Twin during planning when the planning phase is active. Generation currently still returns a baseline-shaped package after building context, so rich generation injection is incomplete.
- `agent/atlas_nexus_web_research_client.py` bridges Atlas planning/generation to the existing Nexus web research pipeline, gated by `ATLAS_NEXUS_WEB_RESEARCH=1`.
- `agent/atlas_llm_json_adapter.py` supports streaming, but Plan/DeepPlanner structured-output paths must be verified and hardened so slow models do not falsely trip stall detection.

## Target Capabilities

### C1. Deep Behavioral Graph

Atlas should infer and persist richer behavior facts:

- Function/method call relationships with import-aware and alias-aware resolution.
- Variable def-use chains across local variables, object fields, class fields, module globals, state dictionaries, config dictionaries, environment variables, and request/session/application state.
- Data-flow edges from user input, request payloads, files, databases, model outputs, generated artifacts, and UI inputs to downstream consumers.
- State transition graphs for `state`, `status`, `phase`, `stage`, `mode`, plan/proposal lifecycle, Portal generated-data lifecycle, Forge route/cutover lifecycle, and repair/convergence lifecycle.
- Resource identity nodes for file paths, database tables, HTTP endpoints, subprocess commands, model routes, artifact paths, Capsule package paths, and external provider calls.
- Read/write/mutate/delete direction on resource effects.
- Transaction and rollback boundaries, including try/except/finally, rollback/abort/revert/undo/compensate calls, retry/backoff/sleep/timeout calls, and convergence/repair signals.
- UI-to-backend paths: DOM event -> JS handler -> API call -> FastAPI route -> backend function -> service/store/resource.
- Test coverage links: changed behavior -> related test functions, fixtures, smoke tests, Play/Portal runtime checks, and evidence collectors.

Every inferred behavioral fact must remain `derivation=heuristic_static`, `status=inferred`, and confidence below verified levels until runtime/verification evidence promotes it.

### C2. Practical Impact Analysis

Atlas should answer:

```text
If I change this file/function/route/state/resource, what can break?
```

Impact Analysis must combine:

- static structural edges;
- behavioral edges;
- source excerpts;
- tests and fixtures;
- runtime observations;
- verification results;
- past incidents and repair records;
- Project Intelligence context;
- optional web research findings when enabled.

The result must include:

- direct impacts;
- transitive impacts;
- affected requirements;
- behavior paths;
- side effects;
- recommended tests;
- past incidents;
- uncertainty and confidence explanations;
- human-readable explanation paths.

### C3. Plan-Time Web Research

When enabled, Atlas should run bounded Nexus web research before or during planning if the requirement benefits from external knowledge.

Research should be used for:

- new APIs, libraries, protocols, UI patterns, browser/platform behavior, model/runtime behavior, hardware/runtime constraints, and framework best practices;
- error diagnostics where upstream issues or documentation may matter;
- greenfield or feature-addition tasks where codebase context alone is insufficient;
- external design or safety constraints.

Research must not run by default. It is enabled by:

```powershell
set ATLAS_NEXUS_WEB_RESEARCH=1
```

Plan-time web research output must be persisted as context packs and reflected in PlanPool metadata, PlanItem rationale, risks, assumptions, and verification strategy.

### C4. Project Intelligence Active Use

Project Intelligence should be actively used when enabled:

```powershell
set CODEAGENT_PROJECT_INTELLIGENCE_ENABLED=1
set CODEAGENT_PROJECT_INTELLIGENCE_SHADOW=0
set CODEAGENT_PROJECT_INTELLIGENCE_PHASES=planning,generation,verification,repair
```

Planning must use active Project Intelligence context.

Generation must stop merely building Twin context and then returning a baseline generation package. It must inject relevant symbols, behavior paths, side effects, preserve behaviors, tests, uncertainties, and convergence gaps into Proposal / Patch Generation / Repair prompts without becoming execution authority.

Verification and Repair must ingest observations and update the Twin/Convergence evidence where safe.

### C5. Slow-Model LLM Timeout Hardening

Atlas planning must support slow local models where first token can take several minutes.

Timeout handling must distinguish:

- first-token timeout;
- token-idle timeout after generation has started;
- total timeout;
- transport/socket timeout;
- structured-output parse/validation retry exhaustion.

A streaming or heartbeat-aware progress path must reset idle timers on real progress.

The implementation must expose metadata such as:

```text
llm_started
llm_first_token
llm_token_delta
llm_heartbeat
llm_idle_waiting
llm_completed
llm_stalled_before_first_token
llm_stalled_after_progress
llm_total_timeout
```

No slow but progressing model should be reported as stalled only because the initial timer was not reset after token generation began.

## Package Sequence

### PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening

Priority: highest.

Reason: if Plan cannot complete with slow models, every downstream feature is blocked.

Scope:

- Inspect all Plan/DeepPlanner/structured-output LLM paths.
- Ensure the real adapter receives progress callbacks or `stream=True` for long planning calls when streaming is enabled.
- Add phase-aware timeout configuration.
- Split first-token, idle-token, and total timeout semantics.
- Record progress events in journal/status metadata.
- Preserve fallback behavior and structured-output validation.

Expected files:

- `agent/atlas_llm_json_adapter.py`
- `agent/atlas_llm_json_adapter_schema.py`
- `agent/atlas_structured_output.py`
- `agent/deep_planner.py`
- Atlas PlanPool / pipeline callers that construct the LLM adapter
- tests covering slow first token and token progress reset

Acceptance:

- A fake streaming backend that waits before first token longer than the old stall window can still succeed when within `first_token_timeout_seconds`.
- A fake backend that emits tokens slowly but continuously does not stall.
- A fake backend that emits one token then stalls beyond idle timeout returns `llm_stalled_after_progress`.
- A fake backend that never emits first token returns `llm_stalled_before_first_token`.
- Existing non-streaming tests continue to pass.
- Status metadata distinguishes the timeout phase.

### PIBIH-2: Impact Analysis Core

Scope:

- Implement or harden Store/Module impact traversal for `ImpactRequest` / `ImpactResult`.
- Traverse structural and behavioral graph edges with depth, confidence, status, and domain filters.
- Separate direct vs transitive impacts.
- Include side effects, behavior paths, recommended tests, and uncertainty.
- Build explanation paths that can be shown in Plan UI and used by Planner.

Expected files:

- `agent/project_twin/store.py`
- `agent/project_twin/module.py`
- `agent/project_twin/contracts.py` only if schema additions are required and backward-compatible
- `tests/test_project_twin_impact_analysis.py`

Acceptance:

- Changing a function returns its direct callers and transitive dependent paths.
- Changing a route returns UI/API callers, backend handler, side effects, and recommended tests when present.
- Changing a state/config/resource ref returns related writers/readers and tests.
- Low-confidence inferred links are included with uncertainty, not as verified certainty.
- Historical risks are included only when requested.

### PIBIH-3: Deep Behavioral Graph V3

Scope:

- Improve Python AST call resolution beyond name-based matching.
- Add import alias and from-import resolution.
- Add module-level symbol table per file.
- Add class/method/self-field detection.
- Add local/global/nonlocal variable def-use graph.
- Add dictionary key/state field tracking for common Atlas lifecycle fields.
- Add request/session/app state and config/env facts.
- Add resource read/write/mutate/delete direction.
- Add transaction/retry/rollback/recovery boundaries.
- Improve JS path extraction and UI-to-API path linking.

Expected files:

- `agent/project_twin/behavioral_graph.py`
- `agent/project_twin/static_graph.py` only for shared resolver helpers if needed
- `tests/test_project_twin_behavioral_graph_v3.py`

Acceptance:

- Def-use edges are stable and deterministic.
- Alias imports resolve to stable canonical refs when possible.
- Ambiguous calls are retained with lower confidence and uncertainty diagnostics.
- Resource effects include direction and resource identity.
- UI event -> API -> route -> handler path is discoverable for a fixture project.
- All new facts remain inferred unless backed by runtime evidence.

### PIBIH-4: Project Intelligence Planning and Generation Injection

Scope:

- Make active planning consume Project Intelligence package in the PlanPool builder/orchestrator path.
- Make generation use rich context rather than building context and returning a baseline-only package.
- Inject relevant symbols, behavior paths, side effects, preserve behaviors, tests, gaps, and uncertainty into Patch Proposal and Repair prompt inputs.
- Keep execution authority with Atlas Proposal / Safe Apply / Verification.

Expected files:

- `agent/project_intelligence/coordinator.py`
- `agent/project_intelligence/adapters/atlas_generation.py`
- `agent/atlas_patch_proposal_service.py`
- PlanPool builder/orchestrator files that prepare planning context
- tests for active/shadow/off rollout behavior

Acceptance:

- With Project Intelligence off, baseline behavior is unchanged.
- With shadow enabled, Twin context is computed and telemetry recorded but planner/generator input is unchanged.
- With planning active, PlanPool metadata includes Project Intelligence context and impact summary.
- With generation active, Proposal payload includes rich Project Intelligence sections.
- Proposal/Safe Apply/Verification boundaries are unchanged.

### PIBIH-5: Plan-Time Nexus Web Research

Scope:

- Add a bounded pre-planning research decision step.
- Decide whether web research is useful based on requirement type, uncertainty, external API/library/framework references, UI/browser/platform terms, and user preference.
- Call `AtlasNexusResearchAdapter` with `AtlasNexusWebResearchClient` only when enabled.
- Save context packs and attach summaries to PlanPool and PlanItem rationale/risk/verification fields.
- Surface warnings truthfully when disabled or unavailable.

Expected files:

- `agent/atlas_nexus_web_research_client.py`
- `agent/atlas_nexus_research_adapter.py`
- PlanPool builder/orchestrator files
- `agent/nexus_context_builder.py` if context composition needs extension
- tests for enabled/disabled/unavailable behavior

Acceptance:

- Default run does not call web research and records no false external evidence.
- Enabled run calls bounded Nexus research for eligible planning requests.
- Disabled/unavailable research returns warnings and does not fail planning.
- Plan output references research as advisory context, not authoritative proof.

### PIBIH-6: Impact UI / Planner Exposure

Scope:

- Expose impact summary to Atlas Workbench planning UI and/or PlanPool markdown.
- Add an Impact section for each PlanItem where target refs are known.
- Provide copyable explanation paths and recommended tests.
- Keep UI thin; server remains authority.

Expected files:

- Atlas API route that returns PlanPool/PlanItem projection
- `web/js/atlas_*` files or equivalent current UI modules
- markdown renderers for PlanPool/Proposal artifacts
- tests or smoke checks for UI projection

Acceptance:

- Plan UI shows impacted files/functions/routes/tests/side effects for a fixture project.
- Unknown impact is shown as uncertainty, not as no risk.
- Recommended tests are visible and tied to graph/evidence reasons.

### PIBIH-7: Runtime Evidence Promotion and Historical Risk Memory

Scope:

- Ingest verification and runtime observations into Twin.
- Promote repeated verified observations to higher confidence where policy allows.
- Link failures/repairs to affected refs as historical risks.
- Ensure false positives are not promoted.

Expected files:

- `agent/project_intelligence/coordinator.py`
- `agent/project_twin/module.py`
- runtime/verification evidence adapters
- tests for observation ingest and historical risk retrieval

Acceptance:

- Passing runtime evidence can support confidence increase without marking unrelated inferred facts verified.
- Failed verification produces historical risk facts linked to affected refs.
- Future impact analysis can include past incidents when `include_historical_risks=True`.

## Implementation Rules

For each package:

1. Read `AGENTS.md` and this plan.
2. Read the current status file and select the next package.
3. Verify current code before editing.
4. Add or update failing tests first where practical.
5. Implement the smallest coherent vertical slice.
6. Preserve off/shadow/active rollout behavior.
7. Preserve all authority boundaries.
8. Run focused tests and affected tests.
9. Record unavailable evidence truthfully.
10. Update the status file before moving to the next package.

## Environment Presets

Local-only active Project Intelligence without web research:

```powershell
set CODEAGENT_PROJECT_INTELLIGENCE_ENABLED=1
set CODEAGENT_PROJECT_INTELLIGENCE_SHADOW=0
set CODEAGENT_PROJECT_INTELLIGENCE_PHASES=planning,generation,verification,repair
set ATLAS_NEXUS_WEB_RESEARCH=0
```

Active Project Intelligence with bounded web research:

```powershell
set CODEAGENT_PROJECT_INTELLIGENCE_ENABLED=1
set CODEAGENT_PROJECT_INTELLIGENCE_SHADOW=0
set CODEAGENT_PROJECT_INTELLIGENCE_PHASES=planning,generation,verification,repair
set ATLAS_NEXUS_WEB_RESEARCH=1
```

Slow local model planning hardening:

```powershell
set ATLAS_LLM_STREAMING=1
set ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=600
set ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=180
set ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=1800
```

If these env names do not yet exist, implement them in PIBIH-1 with backward-compatible defaults.

## Completion Criteria

Do not mark PIBIH complete until:

- slow local planning models can complete or fail with phase-specific timeout reasons;
- Impact Analysis returns direct/transitive impacts, side effects, tests, and uncertainty for realistic fixture projects;
- Behavioral Graph V3 captures function, variable, state, resource, and UI/API paths with deterministic refs;
- Project Intelligence active planning and generation both use rich context;
- Plan-time Nexus Web Research is bounded, gated, persisted, and reflected in planning when enabled;
- UI/PlanPool artifacts show impact summaries and recommended tests;
- runtime/verification evidence can feed future impact risk without false verification claims;
- all safety boundaries above remain intact.
