# Atlas Portal + Model Forge — Detailed Design

## 1. Design principle

The system is split by authority, not by UI screen.

```text
Atlas      = requirement, plan, proposal, Safe Apply, verification, convergence.
Portal     = execution, preview, generated data lifecycle, Capsule lifecycle.
Forge      = provider/model/route selection, evaluation, scoring, rollout of model execution paths.
```

No component may silently take another component's authority.

- Forge never mutates source directly.
- Portal never creates arbitrary command execution.
- Atlas never treats Forge candidate output as applied work before Proposal/Safe Apply.
- Capsule package export remains data-free by default.
- External model providers never receive source unless the configured privacy mode allows it.

## 2. Existing baseline to preserve

Portal / Play / Capsule already provide:

- structured launch adapters;
- session preview for static HTML/assets;
- reverse proxy for ASGI HTTP/SSE/WebSocket;
- Portal catalog/import/export/run/stop;
- Save/Snapshot/Discard runtime data decisions;
- heartbeat/disconnect/resume;
- Capsule builder and Portal catalog UI;
- Fork to Atlas;
- package export without runtime data;
- import quarantine;
- mobile smoke coverage.

Forge must integrate with this instead of replacing it.

## 3. New package layout

Recommended new modules:

```text
agent/model_forge/
  __init__.py
  schema.py
  stage_taxonomy.py
  route_taxonomy.py
  source_policy.py
  provider_registry.py
  provider_base.py
  model_registry.py
  profile_store.py
  benchmark_presets.py
  arena_runner.py
  candidate_evaluator.py
  route_selector.py
  stage_model_selector.py
  profile_updater.py
  rollout.py
  evidence.py
  providers/
    __init__.py
    legacy_atlas.py
    local_openai_compatible.py
    openrouter_config.py
    openrouter_client.py
    openrouter_catalog.py

app/api/model_forge.py
app/api/portal_forge.py

web/js/forge.js
web/js/forge_api.js
web/js/forge_state.js
web/js/forge_ui.js

web/css/forge.css or integrated app.css sections

docs/atlas_portal_forge_*.md
```

Keep implementation modular and interface-first. Do not let UI modules import provider internals. Do not let provider code import FastAPI routers.

## 4. Core schemas

### ProviderDescriptor

```json
{
  "provider_id": "openrouter",
  "provider_type": "openrouter",
  "source_class": "external_cloud",
  "enabled": false,
  "credential_env": "OPENROUTER_API_KEY",
  "base_url": "https://openrouter.ai/api/v1",
  "supports": {
    "chat_completions": true,
    "streaming": false,
    "model_catalog": true,
    "tool_calling": "model_dependent",
    "structured_outputs": "model_dependent"
  },
  "privacy_capabilities": ["no_external_code", "symbol_summary_only", "redacted_only", "full_source_allowed"]
}
```

### ModelDescriptor

```json
{
  "model_id": "qwen-coder-32b-q4-local",
  "provider_id": "llama_cpp_local",
  "display_name": "Qwen Coder 32B Q4",
  "source_class": "local",
  "context_window": 32768,
  "modalities": ["text"],
  "cost_profile": "hardware_local",
  "privacy_profile": "offline",
  "capability_tags": ["coder", "patch", "repair"]
}
```

### ForgeExecutionRequest

```json
{
  "request_id": "forge_req_...",
  "stage": "patch_generation",
  "route_id": "patch_dsl",
  "task_category": "web_app",
  "risk_level": "medium",
  "source_mode": "local_preferred",
  "privacy_mode": "no_external_code",
  "candidate_models": ["qwen-coder-32b-q4-local"],
  "context_package_ref": "...",
  "output_contract": "patch_dsl_v1",
  "verification_contract": "focused_tests_required"
}
```

### ForgeExecutionResult

```json
{
  "request_id": "forge_req_...",
  "provider_id": "llama_cpp_local",
  "model_id": "qwen-coder-32b-q4-local",
  "route_id": "patch_dsl",
  "stage": "patch_generation",
  "raw_output_ref": "...",
  "parsed_output_ref": "...",
  "contract_valid": true,
  "latency_ms": 1234,
  "usage": {"input_tokens": 1000, "output_tokens": 400},
  "errors": [],
  "evidence_refs": []
}
```

### ArenaCandidate

```json
{
  "candidate_id": "cand_...",
  "arena_run_id": "arena_...",
  "model_id": "...",
  "provider_id": "...",
  "route_id": "...",
  "preset_id": "web_app_standard",
  "task_id": "fastapi_route_add",
  "execution_result_ref": "...",
  "score_ref": "...",
  "adoption_state": "not_applied"
}
```

Candidate adoption states:

```text
not_applied
rejected
selected_for_proposal
proposal_created
safe_applied
verified
portal_run_started
portal_run_passed
capsule_created
profile_recorded
```

Arena output must never skip Proposal/Safe Apply.

### CandidateScore

```json
{
  "candidate_id": "cand_...",
  "scores": {
    "format": 1.0,
    "schema": 1.0,
    "syntax": 1.0,
    "focused_tests": 0.9,
    "runtime_evidence": 0.8,
    "requirement_coverage": 0.9,
    "diff_minimality": 0.8,
    "risk": 0.1,
    "latency": 0.7,
    "cost": 1.0,
    "privacy": 1.0
  },
  "final_score": 0.86,
  "verdict": "candidate_eligible_for_proposal",
  "blocked_reasons": []
}
```

## 5. Stage taxonomy

Use stable stage IDs:

```text
requirement_analysis
change_classification
planning
blueprint
context_selection
patch_generation
test_generation
failure_classification
repair
review
verification_interpretation
convergence_decision
final_summary
```

Each stage can have a mode:

```text
disabled
fixed_model
shadow_select
auto_select
arena_select
fallback_only
```

Default rollout:

```text
planning: shadow_select
patch_generation: shadow_select
failure_classification: shadow_select
repair: shadow_select
review: shadow_select
final_summary: disabled or fixed_model
```

Cutover to `auto_select` or `arena_select` requires evidence.

## 6. Route taxonomy

Use stable route IDs:

```text
deterministic
micro_patch
direct_patch
patch_dsl
test_first
repair_loop
sliced_impact
blueprint_slice
critical_gate
greenfield_skeleton
portal_replay_repair
```

Route selection is independent from model selection. Forge must score route x model combinations.

## 7. Source and privacy policy

### Source modes

```text
local_only
local_preferred
hybrid
frontier_preferred
frontier_only
```

### Privacy modes

```text
no_external_code
symbol_summary_only
redacted_only
full_source_allowed
```

Default matrix:

| Stage | Default external policy |
|---|---|
| requirement_analysis | symbol_summary_only |
| planning | symbol_summary_only |
| blueprint | redacted_only |
| context_selection | no_external_code |
| patch_generation | no_external_code |
| test_generation | no_external_code |
| failure_classification | redacted_only |
| repair | no_external_code |
| review | redacted_only |
| final_summary | symbol_summary_only |

A user can raise the policy through Forge UI, but policy changes must be explicit, persisted, visible, and auditable.

## 8. Provider registry

Providers are registered by configuration and health state.

Initial providers:

```text
legacy_atlas
local_openai_compatible
openrouter
```

Later providers:

```text
llama_cpp_native
ollama
vllm
lm_studio
custom_openai_compatible
```

Each provider must implement:

```text
list_models(optional)
health_check
execute_chat_completion
supports_contract
estimate_cost(optional)
redact_request_for_log
```

Provider code must be testable with mocks and must fail closed on missing credentials or disabled state.

## 9. OpenRouter provider design

OpenRouter provider modules:

```text
openrouter_config.py
openrouter_client.py
openrouter_catalog.py
```

Config fields:

```text
enabled
api_key_env
http_referer_env
app_title
base_url
request_timeout_seconds
catalog_cache_ttl_seconds
max_retries
allow_streaming
```

Security requirements:

- never write API key to disk;
- never print Authorization header;
- log only provider_id/model_id/status/latency/usage;
- default enabled=false;
- live smoke disabled unless `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY` exist;
- Local Only mode blocks OpenRouter before request construction.

Request policy mapping:

```text
Forge cost_policy -> OpenRouter provider preference / max price when available
Forge privacy_policy -> provider data/logging constraints when available
Forge latency_policy -> provider sort/preference when available
```

Do not rely exclusively on OpenRouter routing for Atlas safety. Forge still owns stage privacy, redaction, and candidate verification.

## 10. Benchmark presets

Preset schema:

```json
{
  "preset_id": "web_app_standard",
  "display_name": "Web App",
  "category": "web_app",
  "depth": "standard",
  "tasks": ["fastapi_route_add", "html_form_api_call"],
  "required_evaluators": ["syntax", "focused_tests", "api_smoke", "portal_preview"],
  "recommended_routes": ["patch_dsl", "sliced_impact", "test_first"],
  "risk_level": "medium",
  "runtime_budget_seconds": 600,
  "profile_dimensions": ["web_app", "api_backend", "multi_file"]
}
```

Task families:

- Quick: JSON/DSL adherence, one-function patch, import repair, failure classification.
- Web App: FastAPI/HTML/JS/API/UI integration and browser smoke.
- Game / Canvas: draw loop, input, collision, score, restart, timing.
- UI / Visual: responsive cards, modal, state changes, mobile view.
- DB / Persistence: SQLite CRUD, restart persistence, transaction/migration risk.
- Repair: syntax/import/test/runtime/visual failure repair.
- Greenfield: single HTML, small ASGI app, minimal package and Portal run.

## 11. Candidate evaluator

Evaluator order:

```text
contract parse
schema/format
syntax/static checks
workspace policy
focused tests
related tests
Portal preview/runtime evidence
visual/runtime contract
requirement coverage
risk/minimality
cost/latency/privacy penalties
```

Reject immediately when:

- output contract invalid;
- unrelated file edit detected;
- test deletion or weakening detected;
- public API changed without Blueprint approval;
- external privacy policy violated;
- Portal runtime unsafe path detected;
- unavailable check is reported as passed;
- candidate tries to bypass Safe Apply.

LLM review may be advisory only and must not override mechanical failure.

## 12. Model profile store

Store under:

```text
ca_data/model_forge/profiles/
ca_data/model_forge/arena_runs/
ca_data/model_forge/evidence/
ca_data/model_forge/catalog/
```

Profile dimensions:

```text
overall
planning
patch_generation
test_generation
failure_classification
repair
review
json_dsl
web_app
game_canvas
ui_visual
api_backend
db_persistence
multi_file
greenfield
speed
cost
privacy
stability
```

Profile update inputs:

- benchmark preset results;
- Arena candidate scores;
- real Atlas verification reports;
- Portal run evidence;
- Capsule replay evidence;
- user save/discard/Capsule decisions as weak feedback, never as sole proof.

Profile updates must be versioned and reversible. Do not overwrite raw evidence.

## 13. Portal x Forge data flow

### Build flow

```text
Requirement
 -> Atlas planning/proposal
 -> Forge selects stage model/route or runs Arena
 -> Candidate Evaluator selects eligible candidate
 -> Proposal/Safe Apply applies candidate
 -> Verification runs
 -> Portal runs generated artifact
 -> Portal Save/Snapshot/Discard/Capsule decision
 -> Forge profile update
```

### Portal Run metadata

Portal run records should add optional Forge trace:

```json
{
  "forge_trace": {
    "loadout_id": "local_safe",
    "source_mode": "local_only",
    "stage_policy_id": "default_shadow_v1",
    "route_id": "greenfield_skeleton",
    "provider_id": "legacy_atlas",
    "model_id": "configured_local_model",
    "preset_id": "greenfield_quick",
    "arena_run_id": null,
    "candidate_id": null,
    "candidate_score": null,
    "selection_reason": ["legacy primary before cutover"]
  }
}
```

### Capsule manifest extension

Capsule manifests may include a read-only Forge projection:

```json
{
  "forge": {
    "created_by_model_id": "...",
    "created_by_provider_id": "...",
    "route_id": "...",
    "preset_id": "...",
    "verification_ref": "...",
    "portal_replay_refs": []
  }
}
```

Do not mutate immutable package archive contents after creation. Use sidecar metadata if the package already exists.

## 14. UI design

Top-level nav:

```text
Lumen | Atlas | Nexus | Echo | Forge | Portal
```

If Models remains temporarily, keep it secondary and plan migration into Forge.

### Forge overview

Default view should be simple:

- Active Loadout card.
- Source Mode segmented control.
- Provider health row.
- Champions row: Patch, Repair, Review, Web App, Game.
- Recent Arena result.
- Advanced drawer for Stage Matrix and Route Matrix.

### Portal trace

Portal run sheet should show a compact trace:

```text
Built with: Qwen Coder 32B Q4 via Patch DSL
Verified: tests passed, preview passed
Data: ephemeral / saved / snapshot / discarded
[Details]
```

Details expands into provider, model, route, preset, candidate, score, latency, cost, privacy, evidence refs.

### Visual style

Modern but restrained:

- card-based layout;
- one primary action per area;
- compact status pills;
- collapsible expert controls;
- mobile-first responsive grids;
- no dense permanent matrix on default screen;
- avoid visually noisy dashboards.

## 15. Rollout and retirement

Legacy retirement sequence by stage:

```text
legacy primary
 -> Forge shadow
 -> Forge primary with legacy fallback
 -> Forge primary only
 -> legacy retired
```

Required evidence before stage cutover:

- shadow parity or superiority;
- no false success increase;
- no unrelated edit increase;
- rollback tested;
- focused and affected tests pass;
- at least one real configured-model or truthful unavailable evidence run when required;
- Portal evidence when stage output produces runnable artifacts.

Required evidence before legacy deletion:

- consumer-zero registry;
- real benchmark comparison;
- data migration/sidecar compatibility;
- rollback-before-removal proof;
- docs updated;
- owner approval if deletion is broad.
