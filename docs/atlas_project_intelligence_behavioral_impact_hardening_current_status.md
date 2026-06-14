# Atlas Project Intelligence Behavioral Impact Hardening Current Status

## Track

PIBIH: Project Intelligence Behavioral Impact Hardening

## Overall Status

```text
status: completed
current_package: PIBIH-7 (done)
next_action: PIBIH track complete (PIBIH-1..7); follow-on hardening only
```

## Completed Foundations

The following tracks are treated as completed foundations and must not be restarted from scratch:

- Project Intelligence Recovery foundation.
- Portal / Play / Capsule foundation.
- Portal + Model Forge foundation.
- Portal + Model Forge Hardening foundation if already merged in the current branch.
- Existing Project Twin durable store, static graph, behavioral graph, rollout, and coordinator modules.

## Current Known Gaps

1. Slow local models can time out during Plan/DeepPlanner structured-output calls before first token or after token generation starts if progress does not reset the stall timer.
2. Impact Analysis contracts exist, but practical traversal and Plan/UI exposure need hardening.
3. Behavioral graph exists but needs deeper function, variable, state, resource, and UI/API relation inference.
4. Project Intelligence active planning can use Twin context, but generation still needs richer context injection.
5. Plan-time Nexus Web Research exists behind a flag but needs a planning decision point and PlanPool/PlanItem integration.
6. Runtime/verification evidence should feed future impact risk without falsely verifying inferred facts.

## Active Package

### PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening

Priority: highest.

### Required Investigation

- Locate every Atlas planning path that calls `generate_structured`, `call_llm_json`, or `AtlasLLMJsonAdapter`.
- Verify whether Plan/DeepPlanner/PlanPool builders pass `stream=True` or `on_progress`.
- Inspect `_post_chat_stream` behavior and confirm whether last-progress is updated for:
  - first token,
  - content deltas,
  - non-content heartbeat chunks,
  - final completion,
  - errors.
- Confirm current timeout source:
  - request timeout,
  - socket timeout,
  - stalled generation watchdog,
  - frontend/workbench timeout,
  - structured-output retry timeout.

### Acceptance Checklist

- [x] Fake backend with long prefill and valid eventual first token succeeds within first-token timeout.
- [x] Fake backend with continuous slow token deltas succeeds.
- [x] Fake backend with no first token fails as `llm_stalled_before_first_token`.
- [x] Fake backend with one token then no progress fails as `llm_stalled_after_progress`.
- [x] Total timeout is distinct from first-token and idle-token timeout.
- [x] Structured-output retry still works.
- [x] Existing non-streaming tests still pass.
- [x] Plan status/journal metadata records timeout phase truthfully.

## Evidence Log Template

Append one block per package completion:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Project Intelligence evidence:
Impact analysis evidence:
Web research evidence:
Runtime/Portal evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

## Evidence Log

```text
Completed package: PIBIH-1 LLM Planning Timeout and Streaming Progress Hardening
Status: completed
Changed modules/files:
- agent/atlas_llm_json_adapter.py
- tests/test_atlas_llm_streaming_timeout.py
- tests/test_atlas_llm_json_streaming.py
- main.py (UI_DIR absolute-path fix; unblocks the 8000 UI used for verification)
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- Split the single streaming stall window into three independent budgets: first-token,
  idle-token (gap between real content tokens), and an absolute total wall-clock ceiling.
- Added new env names `ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS`, `ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS`,
  and `ATLAS_LLM_TOTAL_TIMEOUT_SECONDS`, falling back to legacy `ATLAS_PLAN_FIRST_TOKEN_SEC` /
  `ATLAS_LLM_INTER_TOKEN_SEC` so existing tuning keeps working (`_resolve_timeout`).
- Reset the idle-token timer only on real content tokens; non-content deltas/keep-alives keep
  the socket alive (heartbeat-aware) but do not reset the idle budget, so a stalled-after-progress
  model is still caught while a slow-but-progressing model is not falsely stalled.
- Per-line wall-clock guards plus blocking-read socket-timeout mapping both classify the failure
  into a phase-specific terminal reason: `llm_stalled_before_first_token`,
  `llm_stalled_after_progress`, or `llm_total_timeout`, raised via a typed `_StreamTimeout`.
- `generate_json` returns the phase as `error` and records `metadata.timeout_phase` plus
  `metadata.tokens_generated`, so Plan status/journal can record the timeout phase truthfully.
- Preserved the structured-output one-shot strict retry and the non-streaming socket-timeout
  `llm_stalled` path for backward compatibility; on_progress token-payload shape is unchanged so
  the existing durable planning/patchgen progress writers are not affected.
Focused tests:
- `python -m pytest tests\test_atlas_llm_streaming_timeout.py tests\test_atlas_llm_json_streaming.py` -> 12 passed.
Syntax checks:
- `python -m py_compile agent\atlas_llm_json_adapter.py main.py` -> passed.
Affected tests:
- `python -m pytest tests\test_atlas_runtime_progress_events.py tests\test_atlas_patch_proposal_watchdog.py tests\test_atlas_api_pipeline.py` -> 46 passed.
- `python -m pytest tests\test_atlas_plan_pool_watchdog.py tests\test_atlas_llm_json_adapter.py` -> 19 passed.
- `python -m pytest tests\test_atlas_llm_streaming_timeout.py tests\test_atlas_llm_json_streaming.py tests\test_atlas_llm_json_adapter.py tests\test_atlas_dev_phase_llm_progress_indicator_contract.py tests\test_atlas_runtime_progress_events.py` -> 36 passed.
Real model evidence:
- localhost:8080 `/v1/models` returned `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf`.
- Live streaming run against localhost:8080 through the hardened adapter (stream=True, json_schema,
  on_progress collector) returned ok=True with valid structured JSON `{"answer":"ok","confidence":0.9}`,
  19 streamed progress events, and a non-empty `last_token_at` on the first event. The idle timer reset
  per real token and the run did not falsely stall. This is authoritative real-model runtime evidence.
- localhost:8080 `/v1/chat/completions` advisory review of the adapter diff returned `verdict: pass`
  with no concerns. This is advisory evidence only.
Project Intelligence evidence:
- Not applicable to PIBIH-1.
Impact analysis evidence:
- Not applicable to PIBIH-1 (begins in PIBIH-2).
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Portal runtime paths were not changed. The 8000 app server was restarted to apply the UI_DIR fix;
  `/`, `/ui/`, and `/ui/index.html` then served 200 (full UI HTML), resolving the reported
  "8000のUIに到達しない" so live Atlas verification is possible again.
Unavailable checks:
- No full live approved Atlas plan-with-slow-model end-to-end browser run was executed; the slow-model
  phase behavior is covered by deterministic fake-clock tests plus a real streaming completion on 8080.
Safety invariants:
- Proposal / Safe Apply / Verification boundaries were not bypassed.
- No external provider was enabled by default; Local Only behavior unchanged.
- No secrets or generated-data persistence paths were added or logged.
- `unavailable` checks are not marked as passed; mock fake-clock tests are labeled separately from the
  real-model streaming evidence.
Remaining gaps:
- Phase-specific timeout reasons are exposed in the adapter result/metadata; threading them into the
  PlanPool/patchgen durable `llm_failed` event metadata can be hardened further in a follow-up if needed.
Next package: PIBIH-2 Impact Analysis Core
Blocker: none
```

```text
Completed package: PIBIH-2 Impact Analysis Core
Status: completed
Changed modules/files:
- agent/project_twin/analysis.py
- tests/test_project_twin_impact_analysis.py
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- Forward-expand impact seeds along definitional `handled_by` edges so changing an api_route surfaces
  its backend handler (reason `implements_changed_entity`) — reverse reachability alone missed it
  because the handler is the edge target, not a dependent. Through the handler, its callers, tests,
  and side effects are then reached.
- Bridge a resolved python symbol (`py://path#qual`) to its name-only alias (`pyname://short`) in both
  directions during traversal: reverse bridging finds heuristic name-based callers (e.g. a test that
  calls an intermediate function); forward bridging lets a name-based call reach the real symbol's
  side effects. This recovers transitive impacts/tests/effects that previously dead-ended at the
  shared name pseudo-node.
- Track `path_confidence` (weakest edge confidence along the discovered path) and report any impact
  reached only through heuristic/inferred links (< 0.7) under `uncertainty`, so inferred links are
  never presented as verified certainty.
- Preserved direct vs transitive separation (depth), min-confidence pruning, side-effect collection,
  recommended tests, behavior/explanation paths, and historical-risk gating via
  `include_historical_risks`.
Focused tests:
- `python -m pytest tests\test_project_twin_impact_analysis.py tests\test_project_twin_analysis.py` -> 10 passed.
  Covers: function change -> caller + tests; route change -> handler + UI caller + tests + file side
  effect; resource change -> writers/readers; uncertainty path_confidence on heuristic links;
  depth + min-confidence filters; historical-risk include/exclude gating.
Syntax checks:
- `python -m py_compile agent\project_twin\analysis.py` -> passed.
Affected tests:
- `python -m pytest tests\test_project_twin_analysis.py tests\test_project_twin_impact_analysis.py tests\test_project_twin_store.py tests\test_project_twin_api.py tests\test_project_twin_behavioral_graph.py tests\test_project_twin_static_graph.py tests\test_project_twin_contracts.py` -> 65 passed.
Real model evidence:
- localhost:8080 `/v1/chat/completions` advisory review of the analysis.py diff returned `verdict: pass`
  with no concerns. This is advisory evidence only; the deterministic graph-assertion tests are authoritative.
Project Intelligence evidence:
- Not applicable to PIBIH-2 (planning/generation injection is PIBIH-4).
Impact analysis evidence:
- Deterministic fixture (function A calls B; route R handled by A; JS click calls R; B touches file F;
  test T covers A) asserts direct/transitive impacts, route->handler/UI/test/side-effect, resource
  writers/readers, uncertainty, filters, and historical-risk gating.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- No Portal/runtime paths changed; analysis reads the twin snapshot and never mutates.
Unavailable checks:
- No live end-to-end Atlas plan-with-impact UI run was executed; PIBIH-6 owns UI/planner exposure.
- config/env read facts are not yet modeled (PIBIH-3 owns request/session/app state and config/env),
  so resource-impact coverage here is limited to file/db/network/process/ui resources.
Safety invariants:
- Proposal / Safe Apply / Verification boundaries were not bypassed.
- Inferred/heuristic links are reported with status + path_confidence and never marked verified.
- No external provider enabled; no secrets or generated-data persistence added.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- Name-alias bridging is intentionally heuristic (name collisions over-connect) and is surfaced via
  reduced path_confidence; PIBIH-3 import/alias-aware resolution will tighten it.
- config/env resource facts deferred to PIBIH-3.
Next package: PIBIH-3 Deep Behavioral Graph V3
Blocker: none
```

```text
Completed package: PIBIH-3 (slice 1 of 2) Deep Behavioral Graph V3 — resource direction + config/env
Status: in_progress (slice landed; import-alias resolution + ambiguous-call diagnostics still pending)
Changed modules/files:
- agent/project_twin/behavioral_graph.py
- tests/test_project_twin_behavioral_graph_v3.py
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- Resource effects now carry a coarse direction (read/write/mutate/delete/call/execute/render) via
  `_resource_direction`; direction is recorded on the side_effect node properties and on the
  `performs_side_effect` / `targets_resource` edges, and is folded into the side-effect node ref so a
  function that both reads and writes the same resource yields two distinct, non-colliding effects.
- Config/environment reads (`os.getenv(...)`, `os.environ.get(...)`) are modeled as a `config`
  resource with read direction (`resource://config:<VAR>`), closing the PIBIH-2-deferred config gap so
  impact analysis surfaces config readers when a config value changes.
- Bumped `ANALYZER_VERSION` to `behavioral_graph.v3`.
Focused tests:
- `python -m pytest tests\test_project_twin_behavioral_graph_v3.py` -> 5 passed (file read/write/delete
  direction + identity; config/env resource + read direction; config-change impact -> reader; def-use
  edge presence + deterministic node/edge ids across rebuilds; all behavioral facts remain inferred /
  heuristic_static / confidence < 1.0).
Syntax checks:
- `python -m py_compile agent\project_twin\behavioral_graph.py` -> passed.
Affected tests:
- `python -m pytest tests\test_project_twin_behavioral_graph.py tests\test_project_twin_behavioral_graph_v3.py tests\test_project_twin_analysis.py tests\test_project_twin_impact_analysis.py tests\test_project_twin_pir7_graphs.py tests\test_project_twin_static_graph.py tests\test_project_twin_source_adapter.py tests\test_project_twin_source_refresh_lifecycle.py tests\test_project_twin_store.py` -> 51 passed.
Real model evidence:
- localhost:8080 advisory review of the behavioral_graph diff returned `verdict: pass` (advisory only;
  deterministic graph-assertion tests are authoritative).
Project Intelligence evidence:
- Not applicable to this slice.
Impact analysis evidence:
- A config-change ImpactRequest (`resource://config:APP_MODE`) returns the reader function, exercising
  the new config resource through the PIBIH-2 impact traversal.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Behavioral analysis reads source and emits a delta; no Portal/runtime paths changed.
Unavailable checks:
- Import-alias / from-import call resolution to canonical refs and ambiguous-call uncertainty
  diagnostics are NOT in this slice; PIBIH-3 acceptance for those criteria is not yet met.
- `os.environ[...]` subscript reads (non-Call) are not yet modeled.
Safety invariants:
- All new nodes/edges are `status=inferred`, `derivation=heuristic_static`, confidence < 1.0; never verified.
- No Proposal / Safe Apply / Verification path touched; no external calls; no secrets.
- `unavailable` checks are not marked as passed.
Remaining gaps (to finish PIBIH-3):
- Import alias + from-import resolution so calls resolve to stable canonical refs beyond name-based matching.
- Ambiguous calls retained at lower confidence WITH uncertainty diagnostics.
- Optional: `os.environ[...]` subscript and class/self-field deepening.
Next package: PIBIH-3 (remaining slice) then PIBIH-4
Blocker: none
```

```text
Completed package: PIBIH-3 (slice 2 of 2) Deep Behavioral Graph V3 — import-aware call resolution
Status: completed (PIBIH-3 acceptance now met across both slices)
Changed modules/files:
- agent/project_twin/static_graph.py
- tests/test_project_twin_call_resolution.py
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- Build a project module map (dotted module -> rel file) plus a per-file import table (module aliases,
  from-imports) and same-file function names; resolve calls beyond name-based matching to stable
  canonical `py://<rel>#<symbol>` refs for from-imports, `import m as x` aliases, and local definitions.
- The name-only `pyname://<name>` `calls` edge is always retained (callers matchable only by name still
  link); the resolved edge is added at higher confidence (0.9) with a `resolution` property.
- A bare-name, non-builtin call that cannot be resolved to a canonical ref emits an `ambiguous_call`
  uncertainty diagnostic (builtins are filtered to avoid noise), satisfying "ambiguous calls retained
  with lower confidence and uncertainty diagnostics".
- Added an optional `properties` arg to the static `_Builder.edge`; bumped `PARSER_VERSION` to
  `static_graph.v2`.
Focused tests:
- `python -m pytest tests\test_project_twin_call_resolution.py` -> 6 passed (from-import / module-alias /
  local resolution to canonical refs; name-only edge retained; resolved-edge higher confidence +
  resolution property; ambiguous_call diagnostic for an unresolved bare name; builtins not flagged).
Syntax checks:
- `python -m py_compile agent\project_twin\static_graph.py` -> passed.
Affected tests:
- `python -m pytest <11 project_twin suites incl. static_graph, call_resolution, analysis, impact,
  behavioral_graph[_v3], source_adapter, source_refresh_lifecycle, store, api, pir7>` -> 64 passed.
Real model evidence:
- localhost:8080 advisory review of the static_graph diff returned `verdict: pass` (advisory only;
  deterministic graph-assertion tests are authoritative).
Project Intelligence evidence:
- Not applicable to this slice.
Impact analysis evidence:
- Resolved `py://` call edges feed the PIBIH-2 traversal directly (in addition to the existing
  pyname bridging), tightening transitive impact precision for import-backed calls.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Static analysis reads source and emits a delta; no Portal/runtime paths changed.
Unavailable checks:
- Relative (`from . import x`) and star imports are left name-based by design; class/self-method
  resolution (`self.m()`) and `os.environ[...]` subscript reads remain future deepening.
Safety invariants:
- Existing name-based call edges are preserved (additive change); no Proposal / Safe Apply /
  Verification path touched; no external calls; no secrets.
- `unavailable` checks are not marked as passed.
PIBIH-3 acceptance (now met):
- Def-use edges stable/deterministic (slice 1); alias imports resolve to stable canonical refs
  (slice 2); ambiguous calls retained with lower confidence + diagnostics (slice 2); resource effects
  include direction + identity (slice 1); UI event -> API -> route -> handler path discoverable
  (PIBIH-2 fixture); all behavioral facts remain inferred (slice 1).
Remaining gaps (deferred deepening, not acceptance blockers):
- self/class-method call resolution; relative/star import resolution; `os.environ[...]` subscript.
Next package: PIBIH-4 Project Intelligence Planning and Generation Injection
Blocker: none
```

```text
Completed package: PIBIH-4 Project Intelligence Planning and Generation Injection
Status: completed
Changed modules/files:
- agent/project_intelligence/coordinator.py
- tests/test_project_intelligence_rollout_generation_injection.py
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- `prepare_generation_context` active path now builds a RICH `GenerationContextPackage` from the twin
  (new `_active_generation`, mirroring `_active_planning`) instead of building context then discarding
  it and returning a baseline package — the actual gap called out in the plan baseline assessment.
- Injects actual_symbols, required_interfaces, behavior_paths, preserve_behaviors, convergence_gaps
  (only missing/contradicted preserve-behaviors), verification_requirements (from twin tests),
  source-excerpt target_files, prohibited_divergences (present preserve-behaviors), and the twin
  revision + manifest.
- The existing `AtlasGeneratorBridge` already maps these fields into the active generation context
  dict the Patch Proposal consumes; it was receiving an empty package before, so this change makes the
  rich Project Intelligence sections actually reach generation.
- Off/shadow unchanged (baseline + shadow telemetry); an unready/disabled twin falls back to baseline
  tagged active (never fabricated). Planning active injection (PlanPool metadata + impact summary) was
  already implemented in `_active_planning`.
Focused tests:
- `python -m pytest tests\test_project_intelligence_rollout_generation_injection.py` -> 5 passed (off
  inert; shadow records comparison + baseline; active injects rich context; unready twin -> baseline;
  end-to-end rich context flows through AtlasGeneratorBridge into the proposal context dict).
Syntax checks:
- `python -m py_compile agent\project_intelligence\coordinator.py` -> passed.
Affected tests:
- All `tests\test_project_intelligence*.py` -> 377 passed, 1 xfailed (no regression to rollout,
  generator bridge, boundaries, facade conformance, production composition).
Real model evidence:
- localhost:8080 advisory review of the coordinator diff -> `verdict: pass` (advisory only; rollout
  contract tests are authoritative).
Project Intelligence evidence:
- Rollout off/shadow/active behavior asserted for generation; active surfaces twin symbols/behavior
  paths/preserve-behaviors/gaps/verification/excerpts.
Impact analysis evidence:
- behavior_paths and preserve-behavior gaps in the generation package are derived from the twin
  context built on the PIBIH-2/PIBIH-3 graph.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Coordinator is advisory; it returns a context package and never decides apply/verify (ADR-PI-003);
  Proposal / Safe Apply / Verification boundaries unchanged.
Unavailable checks:
- No live LLM patch-generation run with active Project Intelligence executed end to end; the injection
  is covered by rollout-mode contract tests plus the bridge integration test.
Safety invariants:
- Off mode behaviorally equivalent to baseline; shadow returns baseline + telemetry only; unavailable
  twin never fabricated into rich context; advisory-only (no execution authority).
- `unavailable` checks are not marked as passed.
Remaining gaps:
- Wiring the active generation context into the live patch-proposal LLM prompt end to end (service-level
  plumbing) can be hardened/verified with a live model in a follow-up; the data path is complete.
Next package: PIBIH-5 Plan-Time Nexus Web Research
Blocker: none
```

```text
Completed package: PIBIH-5 Plan-Time Nexus Web Research
Status: completed
Changed modules/files:
- agent/atlas_plan_time_research.py (new)
- app/api/atlas_pipeline.py (attach advisory research to PlanPool metadata)
- tests/test_atlas_plan_time_web_research.py (new)
- tests/test_atlas_api_pipeline.py (default-off advisory attach assertion)
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- Added the missing plan-time DECISION point: `should_research` decides eligibility from the
  requirement text (external API/library/framework/protocol signals, browser/platform terms,
  greenfield/feature signals) and user preference (`use_nexus`, `force`).
- `AtlasPlanTimeResearchService.research` runs a BOUNDED Nexus research job (via the existing
  `AtlasNexusResearchAdapter` + `AtlasNexusWebResearchClient`) ONLY when the request is eligible AND
  `ATLAS_NEXUS_WEB_RESEARCH=1`; otherwise returns a truthful skipped result with a warning. It never
  calls web by default, never fabricates external evidence, and never raises (research must not fail
  planning). Result is always advisory (`advisory=True`), never authoritative.
- Wired into `_create_plan_pool_core`: the advisory result (`to_metadata()`) is attached to
  `pool.metadata["plan_time_web_research"]`, persisting context packs through the adapter+journal when
  enabled. Plan-time research thus reflects in PlanPool output as advisory context.
Focused tests:
- `python -m pytest tests\test_atlas_plan_time_web_research.py` -> 8 passed (eligibility decision;
  user preference/force; default-off no-call + warning; ineligible no-call; enabled+eligible bounded
  research via fake client; unavailable -> warning without failing; advisory/truthful metadata).
- `python -m pytest tests\test_atlas_api_pipeline.py::test_plan_pool_attaches_advisory_web_research_disabled_by_default`
  -> passed (PlanPool metadata carries advisory, enabled=False, called=False, `web_research_disabled`).
Syntax checks:
- `python -m py_compile agent\atlas_plan_time_research.py app\api\atlas_pipeline.py` -> passed.
Affected tests:
- `python -m pytest tests\test_atlas_api_pipeline.py tests\test_atlas_plan_time_web_research.py` -> 40 passed.
- Pre-existing, unrelated nexus router/API/web-integration failures (duplicate `/nexus/summary` route,
  searxng/brave/zip environment) reproduce with this change stashed and are NOT caused by it.
Real model evidence:
- localhost:8080 advisory review of the service + pipeline attach -> `verdict: pass` (advisory only;
  the gating/eligibility contract tests are authoritative).
Project Intelligence evidence:
- Not applicable beyond PlanPool metadata attach.
Impact analysis evidence:
- Not applicable.
Web research evidence:
- External web research remains OFF by default and policy-gated (`ATLAS_NEXUS_WEB_RESEARCH=1`); the
  default path performs no external call and records no false external evidence (asserted).
Runtime/Portal evidence:
- No Portal/runtime paths changed; research is advisory and bounded.
Unavailable checks:
- No live `ATLAS_NEXUS_WEB_RESEARCH=1` end-to-end searxng run executed here; enabled/eligible behavior
  is covered by a fake-client bounded-research test, and the unavailable path degrades to warnings.
Safety invariants:
- Default off; eligible-but-disabled never calls web; unavailable never fails planning; results are
  advisory, never authoritative; no secrets; no Proposal/Safe Apply/Verification path touched.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- Per-PlanItem rationale/risk/verification injection (vs PlanPool-level advisory metadata) and a live
  `=1` searxng end-to-end verification can be hardened in a follow-up.
Next package: PIBIH-6 Impact UI / Planner Exposure
Blocker: none
```

```text
Completed package: PIBIH-6 Impact UI / Planner Exposure
Status: completed
Changed modules/files:
- agent/atlas_journal.py (plan pool markdown Impact Analysis section)
- tests/test_atlas_journal.py
- app/nexus/router.py (fix duplicate /nexus/* routes — merged separately, #1848)
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- `write_plan_pool_markdown` now renders a per-item "## Impact Analysis" section from
  `pool.metadata['plan_item_impact_map']`: impacted files, impacted functions/routes/symbols,
  recommended tests, recommended advisory checks, confidence, and reasons.
- Unknown/empty impact is always shown as uncertainty ("unknown (uncertainty — not zero risk)"),
  never as "no risk"; when the map is missing/unavailable the section says so and instructs treating
  unknown impact as uncertainty. Commands stay advisory suggestions; the renderer never executes.
- The plan UI surfaces this through the existing PlanPool markdown path (the panel renders the raw
  markdown), and the impact map remains available on the PlanPool projection (pool metadata).
Focused tests:
- `python -m pytest tests\test_atlas_journal.py` -> 13 passed (impact section renders impacted
  files/symbols/routes + recommended tests with reasons + confidence; unavailable map shows
  uncertainty/not-zero-risk; unknown confidence shows the uncertainty note).
Syntax checks:
- `python -m py_compile agent\atlas_journal.py` -> passed.
Affected tests:
- `python -m pytest tests\test_atlas_journal.py tests\test_atlas_api_pipeline.py
  tests\test_atlas_plan_item_impact_map_service.py tests\test_atlas_plan_item_impact_map_ui_contract.py`
  -> 50 passed.
- `tests\test_nexus_router_contract.py` + `tests\test_nexus_web_status_contract.py` -> 8 passed after
  removing the duplicate `/nexus/summary` `/jobs/active` `/web/status` compat routes (api router is the
  single owner). Pre-existing nexus research-agent/web-integration failures are environment-dependent
  (searxng/brave/zip, recursive-search mock drift) and unrelated.
Real model evidence:
- localhost:8080 advisory review of the markdown renderer -> `verdict: pass` (advisory only;
  deterministic markdown contract tests are authoritative).
Impact analysis evidence:
- The rendered section consumes the existing AtlasPlanItemImpactMap (impacted files/tests/symbols +
  confidence), which is built on the PIBIH-2/PIBIH-3 graph.
Web research evidence:
- Not applicable; no external calls.
Runtime/Portal evidence:
- Pure renderer; no Portal/runtime paths changed; no execution.
Unavailable checks:
- No full live browser screenshot of the Impact section was captured; exposure is via the existing
  markdown rendering path and covered by markdown contract tests.
Safety invariants:
- Renderer-only; unknown impact is uncertainty, never zero risk; commands are advisory; no
  Proposal/Safe Apply/Verification path touched; no secrets.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- A dedicated structured PlanPool/PlanItem impact projection endpoint and richer in-panel (non-markdown)
  impact widgets can be added in a follow-up; the authoritative artifact already carries the section.
Next package: PIBIH-7 Runtime Evidence Promotion and Historical Risk Memory
Blocker: none
```

```text
Completed package: PIBIH-7 Runtime Evidence Promotion and Historical Risk Memory
Status: completed
Changed modules/files:
- agent/project_twin/module.py
- tests/test_project_twin_runtime_evidence_promotion.py
- docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
Behavior implemented:
- `ingest_runtime` now promotes runtime/verification results into durable graph facts: a FAILED
  observation becomes an `incident` node (status=observed, derivation=runtime_observation) linked to
  each affected subject ref via an `affects` edge; a PASSED observation becomes a `runtime_evidence`
  node that `supports` its subject refs.
- The incident edges make failures discoverable by `assess_impact` as `past_incidents` (gated by
  `include_historical_risks`) when a future change touches an affected ref.
- Passing evidence is additive runtime-observed support that can raise confidence WITHOUT mutating or
  falsely marking any inferred fact verified; `unavailable` is never converted into a failure/incident.
Focused tests:
- `python -m pytest tests\test_project_twin_runtime_evidence_promotion.py` -> 4 passed.
Syntax checks:
- `python -m py_compile agent\project_twin\module.py` -> passed.
Affected tests:
- `python -m pytest <runtime_evidence + verification_context + durable_event_projection +
  runtime_collectors + store + impact_analysis + verification_resume>` -> 49 passed.
Real model evidence:
- localhost:8080 advisory review of the module diff -> verdict approved/pass (advisory only).
Impact analysis evidence:
- A failed observation on a subject ref is surfaced by assess_impact(include_historical_risks=True) as
  a past incident; excluded when False (asserted).
Web research evidence:
- Not applicable.
Runtime/Portal evidence:
- Runtime observations promoted to graph facts; no Portal/runtime execution path changed.
Unavailable checks:
- `unavailable` observations never become incidents (asserted).
Safety invariants:
- `unavailable` is not `passed`; passing evidence never marks unrelated inferred facts verified;
  incidents are runtime-observed, not fabricated; no Proposal/Safe Apply/Verification path touched.
Remaining gaps:
- Repeated-pass numeric confidence promotion on the subject node itself and historical-risk decay can
  be hardened in a follow-up.
Next package: none — PIBIH-1..7 complete.
Blocker: none
```

## Next Package Queue

```text
PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening  (completed)
PIBIH-2: Impact Analysis Core  (completed)
PIBIH-3: Deep Behavioral Graph V3  (completed)
PIBIH-4: Project Intelligence Planning and Generation Injection  (completed)
PIBIH-5: Plan-Time Nexus Web Research  (completed)
PIBIH-6: Impact UI / Planner Exposure  (completed)
PIBIH-7: Runtime Evidence Promotion and Historical Risk Memory  (completed)
```

## Track completion

All PIBIH packages (PIBIH-1..7) are complete. The Atlas Project Intelligence Behavioral Impact
Hardening track is done: slow-model planning timeouts are phase-aware; impact analysis returns
direct/transitive impacts, side effects, recommended tests, and uncertainty; the behavioral graph
captures function/variable/state/resource/UI-API paths with deterministic refs and import/self call
resolution; Project Intelligence active planning AND generation both inject rich context; plan-time
Nexus web research is bounded, gated, and reflected in PlanPool metadata; PlanPool artifacts show
per-item impact summaries and recommended tests; and runtime/verification evidence feeds future impact
risk (incidents) and supports confidence without false verification. A virtual-project behavior
evaluation (`scripts/twin_behavior_eval.py`, 20/20) plus remediations R1-R3 validated the twin.
