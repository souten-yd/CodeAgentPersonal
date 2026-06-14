# Atlas Project Intelligence Behavioral Impact Hardening Test Plan

## Principles

- Tests must prove behavior, not only adapter shape.
- `unavailable` is not `passed`.
- Inferred graph facts must not be asserted as verified facts.
- Mock tests are allowed for deterministic logic, but live/runtime evidence must be labeled separately.
- Off/shadow/active rollout behavior must be tested for every Project Intelligence integration.

## PIBIH-1 Tests: LLM Planning Timeout and Streaming Progress

### Unit Tests

Create fake streaming backends for:

1. Long first-token wait then valid JSON.
2. Continuous slow token stream.
3. No first token.
4. One token then stall.
5. Total timeout exceeded.
6. Malformed first output then valid structured retry.

Assertions:

- First-token timeout and idle-token timeout are separate.
- `last_progress_at` updates on token deltas.
- `first_token_seen` flips only after content progress.
- Timeout metadata distinguishes `before_first_token`, `after_progress`, and `total_timeout`.
- Existing non-streaming call path remains backward-compatible.

Suggested tests:

```text
tests/test_atlas_llm_streaming_timeout.py
tests/test_atlas_structured_output_timeout_progress.py
```

## PIBIH-2 Tests: Impact Analysis Core

Create a fixture project with:

- function A calls function B;
- route R handled by function A;
- JS event calls route R;
- function B writes file F and reads config C;
- test T covers route R or function A.

Assertions:

- `ImpactRequest(changed_refs=[B])` returns A as direct/transitive impact.
- route R impact includes JS event and backend handler.
- side effects include file/config/resource refs.
- recommended tests include T.
- low-confidence links appear under uncertainty where appropriate.
- depth and min-confidence filters work.

Suggested tests:

```text
tests/test_project_twin_impact_analysis.py
```

## PIBIH-3 Tests: Behavioral Graph V3

Use fixture files covering:

- import alias;
- from-import;
- class methods and `self.field`;
- module globals;
- dictionary state keys;
- environment/config access;
- try/except/finally rollback path;
- retry/backoff path;
- JS event -> fetch -> API path.

Assertions:

- deterministic canonical refs;
- stable node IDs;
- def-use edges;
- resource direction properties;
- lower confidence for ambiguous calls;
- no verified status for static-only facts.

Suggested tests:

```text
tests/test_project_twin_behavioral_graph_v3.py
```

## PIBIH-4 Tests: Project Intelligence Injection

Test rollout modes:

- off: baseline unchanged;
- shadow: computes telemetry but returns baseline inputs;
- active planning: PlanPool metadata includes Twin/impact context;
- active generation: Proposal payload includes symbols, behavior paths, side effects, tests, and uncertainty.

Suggested tests:

```text
tests/test_project_intelligence_rollout_generation_injection.py
tests/test_atlas_plan_pool_project_intelligence_context.py
```

## PIBIH-5 Tests: Plan-Time Nexus Web Research

Test cases:

- disabled by default;
- enabled and eligible requirement calls Nexus client;
- enabled but ineligible requirement does not call web;
- Nexus unavailable returns warning and planning continues;
- research context pack is saved and attached to PlanPool/PlanItem metadata;
- external evidence is labeled advisory.

Suggested tests:

```text
tests/test_atlas_plan_time_web_research.py
```

## PIBIH-6 Tests: Impact UI / Planner Exposure

Test cases:

- PlanPool projection includes impact summaries.
- Plan UI renders impacted refs, side effects, recommended tests, and uncertainty.
- Empty/unknown impact is shown as uncertainty, not no risk.

Suggested tests:

```text
tests/test_atlas_impact_projection.py
```

## PIBIH-7 Tests: Runtime Evidence and Historical Risk

Test cases:

- verification observation is ingested into Twin.
- repeated passing evidence can raise confidence only for the observed subject.
- failed verification creates historical risk linked to changed refs.
- future impact analysis includes past incidents only when requested.

Suggested tests:

```text
tests/test_project_twin_runtime_evidence_promotion.py
tests/test_project_twin_historical_risk_impact.py
```

## Command Guidance

Run focused tests first, then affected tests:

```powershell
python -m pytest tests/test_atlas_llm_streaming_timeout.py -q
python -m pytest tests/test_project_twin_impact_analysis.py -q
python -m pytest tests/test_project_twin_behavioral_graph_v3.py -q
python -m pytest tests/test_project_intelligence_rollout_generation_injection.py -q
```

Run syntax checks for changed modules:

```powershell
python -m py_compile agent/atlas_llm_json_adapter.py
python -m py_compile agent/project_twin/behavioral_graph.py
python -m py_compile agent/project_twin/store.py
python -m py_compile agent/project_intelligence/coordinator.py
```

If live model, web, Portal, or runtime evidence is unavailable, record it as unavailable with reason. Do not mark it passed.
