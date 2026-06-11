# Atlas Portal + Model Forge — Test Plan

## Test philosophy

Use PIR-style proof gates. Test level must match the claim.

```text
unit/component tests       -> component_complete
API/router integration     -> production_connected for API wiring only
Portal runtime execution   -> Portal runtime evidence only when real Portal run occurs
real local model execution -> model execution evidence only when configured model actually runs
OpenRouter live smoke      -> OpenRouter evidence only when opt-in live smoke actually runs
benchmark/cutover          -> acceptance only with comparative reports and rollback evidence
```

Never mark an unavailable check as passed.

## Required test categories

### 1. Contract/schema tests

Targets:

```text
agent/model_forge/schema.py
agent/model_forge/stage_taxonomy.py
agent/model_forge/route_taxonomy.py
agent/model_forge/source_policy.py
```

Assertions:

- valid schema roundtrips;
- invalid stage/route/source/privacy modes fail closed;
- default policies are safe;
- external providers are disabled unless configured;
- candidate adoption states cannot skip Safe Apply/Verification.

### 2. Provider tests

Targets:

```text
agent/model_forge/provider_base.py
agent/model_forge/provider_registry.py
agent/model_forge/providers/legacy_atlas.py
agent/model_forge/providers/local_openai_compatible.py
agent/model_forge/providers/openrouter_client.py
agent/model_forge/providers/openrouter_catalog.py
```

Required cases:

- disabled provider cannot execute;
- missing credential is unavailable, not passed;
- secrets are redacted from logs/results;
- Local Only blocks OpenRouter before request construction;
- mock OpenRouter chat completion normalizes response;
- mock OpenRouter error becomes structured error/unavailable;
- catalog cache falls back offline without claiming live fetch success.

### 3. Benchmark preset tests

Targets:

```text
agent/model_forge/benchmark_presets.py
agent/model_forge/benchmark_presets/*.json
```

Required cases:

- Quick/Web App/Repair/Greenfield presets load;
- each task declares category, risk, evaluators, runtime budget, and allowed routes;
- invalid preset fails with actionable diagnostics;
- depth selection does not run all tasks by default.

### 4. Arena tests

Targets:

```text
agent/model_forge/arena_runner.py
agent/model_forge/arena_store.py
```

Required cases:

- multiple model x route candidates can be generated using mock providers;
- candidates are persisted as `not_applied`;
- no source mutation occurs;
- candidate output cannot bypass Proposal/Safe Apply;
- failed candidates record raw output and rejection reason.

### 5. Candidate evaluator tests

Targets:

```text
agent/model_forge/candidate_evaluator.py
```

Required cases:

- invalid output contract rejected;
- syntax/static failures rejected;
- unavailable evaluator recorded as unavailable;
- unrelated file edits rejected;
- privacy violation rejected;
- candidate with mechanical failure cannot be accepted by LLM review;
- score aggregation preserves blocked reasons.

### 6. Profile store tests

Targets:

```text
agent/model_forge/profile_store.py
agent/model_forge/profile_updater.py
```

Required cases:

- profile update is versioned or append-only;
- raw evidence reference is preserved;
- weak user feedback does not override runtime evidence;
- profile dimensions update per preset;
- profile recomputation from evidence is possible.

### 7. Stage/route selector tests

Targets:

```text
agent/model_forge/stage_model_selector.py
agent/model_forge/route_selector.py
agent/model_forge/rollout.py
```

Required cases:

- disabled/fixed/shadow/auto/arena/fallback modes behave distinctly;
- selector returns reason and confidence;
- critical tasks cannot use unsafe routes;
- external model blocked when privacy/source policy forbids it;
- shadow mode does not change primary execution;
- rollback returns to legacy primary where configured.

### 8. Forge API tests

Targets:

```text
app/api/model_forge.py
app/api/portal_forge.py
```

Required cases:

- provider/model/profile/preset endpoints return safe summaries;
- no secret in any response;
- arena run endpoint cannot apply candidate directly;
- policy update validates unsafe changes;
- disabled provider status is visible but non-executable.

### 9. Forge UI tests

Targets:

```text
ui.html
web/js/forge*.js
web/css/app.css or web/css/forge.css
```

Required cases:

- Forge top-level nav appears with Portal still available;
- mobile Forge tab works;
- Overview renders with empty profiles and no external providers;
- Provider cards redact credential status;
- Benchmark preset selector defaults to Quick/Standard, not Full;
- Arena UI has no direct apply button;
- Stage/Route Matrix is collapsible advanced UI;
- Portal UI remains functional.

Checks:

```text
node --check relevant JS
python scripts/check_ui_inline_script_syntax.py
mobile viewport smoke
focused UI contract tests
```

### 10. Portal polish regression tests

Existing Portal tests must remain green:

```text
tests/test_portal_catalog.py
tests/test_portal_runtime.py
tests/test_portal_data_lifecycle.py
tests/test_portal_recovery_lifecycle.py
tests/test_atlas_capsule_builder.py
tests/test_atlas_play_portal_capsule_acceptance.py
```

Additional Portal polish tests:

- browser upload import quarantine;
- snapshot list and start-from-snapshot;
- legacy manifest sidecar repair;
- Portal run loads with and without Forge trace.

### 11. Portal x Forge integration tests

Targets:

```text
app/api/portal_forge.py
app/portal/*
agent/model_forge/profile_updater.py
```

Required cases:

- Portal run stores optional Forge trace;
- legacy Portal run without trace still loads;
- Portal runtime failure feeds candidate/profile evidence;
- user Save/Snapshot/Discard is recorded;
- Capsule sidecar/manifest includes Forge projection;
- package export remains data-free;
- Capsule replay produces Forge profile evidence.

### 12. Real local model evidence

When a configured local/self-hosted model is available:

```text
Quick preset      -> real provider execution
Web App preset    -> real provider + Portal run where applicable
Repair preset     -> real failure fixture + verified repair
Greenfield preset -> real generation + Portal run + Capsule/replay
```

If the local model is not available, record the check as unavailable and do not mark acceptance for packages requiring real model evidence.

### 13. OpenRouter live smoke

Live smoke is optional and must be opt-in:

Required environment:

```text
FORGE_OPENROUTER_LIVE_SMOKE=1
OPENROUTER_API_KEY=<secret>
```

Assertions:

- request succeeds against a low-cost selected model or records failure truthfully;
- no source is sent unless a test explicitly allows harmless synthetic text;
- logs contain no API key;
- usage/latency/model ID are recorded;
- missing key or flag = unavailable, not passed.

### 14. Cutover and retirement tests

Before Forge becomes primary for any stage:

- legacy-vs-Forge shadow evidence;
- no false success regression;
- no unrelated edit regression;
- rollback proof;
- affected Atlas tests;
- Portal evidence if runnable artifacts are involved.

Before deleting legacy path:

- consumer registry shows consumer-zero or migrated consumers;
- real benchmark comparison;
- data/profile migration evidence;
- rollback-before-removal proof;
- explicit status update.

## Milestone suites

### Milestone A — Portal polish complete

Run:

```text
pytest Portal/Capsule/Play focused tests
node --check Portal-related JS
inline script syntax check
mobile smoke
```

### Milestone B — Forge foundation complete

Run:

```text
model_forge schema/provider/preset/arena/evaluator/profile tests
Forge API tests
no external live calls
```

### Milestone C — Forge UI complete

Run:

```text
Forge JS syntax
Forge API mock UI tests
Portal nav regression
mobile smoke
```

### Milestone D — Portal x Forge complete

Run:

```text
Portal run with Forge trace
Capsule with Forge metadata
Capsule replay updates profile
Portal data lifecycle regression
```

### Milestone E — Real model evidence complete

Run:

```text
Quick/Web App/Repair/Greenfield using configured real local or self-hosted model
OpenRouter live smoke only if explicitly configured
comparative reports generated from artifacts, not manual metrics
```

### Milestone F — Controlled cutover complete

Run:

```text
stage shadow comparison
selected stage Forge primary with legacy fallback
rollback drill
consumer registry check
```

## Evidence record template

Every package current-status update must include:

```text
Completed package:
Status:
Changed modules/files:
Public contracts added or changed:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model / Portal / OpenRouter evidence:
Unavailable checks:
Safety invariants verified:
Migration/rollout state:
Known limitations:
Remaining gaps:
Next package:
Blocker:
```
