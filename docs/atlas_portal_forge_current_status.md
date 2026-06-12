# Atlas Portal + Model Forge — Current Status

> Mutable checkpoint for Codex or Claude goal mode.
> Update this file after every coherent work package.

## Program state

- Overall: **ACTIVE — IMPLEMENTATION READY**
- Active track: `PFG-0..PFG-38`
- Current package: `PFG-28`
- Current package goal: Portal evidence to Candidate Evaluator.
- Next action: feed Portal preview/log/save/discard/snapshot outcomes into the evaluator /
  profile updater; treat user decisions as weak feedback unless paired with runtime evidence.
- Last completed: `PFG-27` (Portal Run Forge Trace metadata) — acceptance_complete; see
  PFG-27 evidence below. PFG-1..PFG-26 also complete.
- Portal baseline: PR-PPC-0 through PR-PPC-12 are complete; Portal UI reconciliation has wired Portal navigation/catalog/run/data decisions into the production shell.
- Project Intelligence baseline: PIR remains active separately. Do not delete or override PIR instructions.
- Rollout: Forge off by default; legacy model execution remains primary until shadow/cutover gates pass.

This file selects the active Portal + Model Forge package. Do not use this status file to claim PIR completion.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_portal_forge_master_goal.md`
3. `docs/atlas_portal_forge_current_status.md`
4. current package in `docs/atlas_portal_forge_implementation_plan.md`
5. relevant sections of `docs/atlas_portal_forge_detailed_design.md`
6. relevant sections of `docs/atlas_portal_forge_test_plan.md`
7. Portal/Capsule baseline docs:
   - `docs/atlas_play_portal_capsule_current_status.md`
   - `docs/atlas_play_portal_capsule_goal.md`
   - `docs/atlas_capsule_portal_spec.md`
8. Project Intelligence recovery docs when touching Atlas/PIR/PlanPool/Proposal/Safe Apply/Verification/Convergence paths:
   - `docs/atlas_project_intelligence_recovery_current_status.md`
   - `docs/atlas_project_intelligence_recovery_master_goal.md`
9. target code, direct callers, dependencies, and tests.

## Confirmed baseline

- Portal top-level navigation exists.
- Portal catalog/run sheet exists.
- Portal data lifecycle includes Save, Snapshot, Discard, backup/delete, heartbeat/disconnect/resume.
- Capsule builder is wired through the UI and calls `buildCapsule`.
- Portal run uses public Portal runtime API, not a second process runner.
- Package Export remains data-free.
- Free-form command execution remains unsupported.
- Portal has known polish gaps:
  - browser upload import endpoint/UI;
  - snapshot-list/start-from-snapshot run selector;
  - legacy package manifest sidecar repair;
  - Forge Trace panel and Portal x Forge metadata.

## Package table

| Package | Goal | Status |
|---|---|---|
| PFG-0 | baseline and design acceptance | acceptance_complete |
| PFG-1 | Portal polish audit and compatibility gates | acceptance_complete |
| PFG-2 | Portal import upload endpoint and UI | acceptance_complete |
| PFG-3 | Portal snapshot listing and start-from-snapshot UI | acceptance_complete |
| PFG-4 | legacy package manifest sidecar repair | acceptance_complete |
| PFG-5 | Forge core schemas and taxonomies | acceptance_complete |
| PFG-6 | provider base and registry | acceptance_complete |
| PFG-7 | Legacy Atlas Executor adapter | acceptance_complete |
| PFG-8 | local OpenAI-compatible provider adapter | acceptance_complete |
| PFG-9 | OpenRouter configuration and secret policy | acceptance_complete |
| PFG-10 | OpenRouter mock chat client | acceptance_complete |
| PFG-11 | OpenRouter model catalog cache | acceptance_complete |
| PFG-12 | provider health and Source Mode policy | acceptance_complete |
| PFG-13 | benchmark preset schema and initial presets | acceptance_complete |
| PFG-14 | Arena runner foundation | acceptance_complete |
| PFG-15 | Candidate Evaluator foundation | acceptance_complete |
| PFG-16 | Model Profile Store and profile updater | acceptance_complete |
| PFG-17 | Stage Matrix policy and selector | acceptance_complete |
| PFG-18 | Route Matrix policy and selector | acceptance_complete |
| PFG-19 | Forge backend API | acceptance_complete |
| PFG-20 | Forge top-level nav and shell UI | acceptance_complete |
| PFG-21 | Forge Overview and Provider cards | acceptance_complete |
| PFG-22 | Skill Radar and Leaderboard UI | acceptance_complete |
| PFG-23 | Benchmark Preset selector UI | acceptance_complete |
| PFG-24 | Arena UI | acceptance_complete |
| PFG-25 | Stage Matrix and Route Matrix UI | acceptance_complete |
| PFG-26 | Loadouts UI and persistence | acceptance_complete |
| PFG-27 | Portal Run Forge Trace metadata | acceptance_complete |
| PFG-28 | Portal evidence to Candidate Evaluator | not_started |
| PFG-29 | Capsule Forge metadata and replay | not_started |
| PFG-30 | real local-model Quick preset run | not_started |
| PFG-31 | real Web App / Portal run preset | not_started |
| PFG-32 | real Repair preset run | not_started |
| PFG-33 | real Greenfield Capsule replay run | not_started |
| PFG-34 | optional OpenRouter live smoke gate | not_started |
| PFG-35 | stage shadow evidence for patch/test/failure/repair | not_started |
| PFG-36 | controlled Forge primary cutover for selected stage | not_started |
| PFG-37 | legacy retirement gates and consumer registry | not_started |
| PFG-38 | final milestone benchmark and docs | not_started |

## Status values

Use only:

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

## Completion rule

Portal + Model Forge remains incomplete until PFG-38 and every required live/model/Portal/rollout gate in `docs/atlas_portal_forge_master_goal.md` pass.

Do not mark the program complete from docs alone, mock provider tests alone, adapter-only tests, UI rendering alone, manually supplied metrics, or unavailable live model/OpenRouter checks.

## Executed package log

```text
Work package: PFG-0 — Baseline and design acceptance
Status: acceptance_complete
Changed modules/files:
- docs/atlas_portal_forge_master_goal.md
- docs/atlas_portal_forge_detailed_design.md
- docs/atlas_portal_forge_implementation_plan.md
- docs/atlas_portal_forge_test_plan.md
- docs/atlas_portal_forge_current_status.md
- docs/atlas_portal_forge_agent_entrypoint.md
- AGENTS.md
Public contracts added or changed:
- Documentation only; no runtime behavior change.
Behavior implemented:
- None; this is the canonical design and Goal entrypoint checkpoint.
Focused tests:
- Not run; docs-only checkpoint.
Syntax checks:
- Not run; docs-only checkpoint.
Affected tests:
- Not run; docs-only checkpoint.
Real model / Portal / OpenRouter evidence:
- None claimed.
Unavailable checks:
- No live model, Portal runtime, or OpenRouter execution claimed in PFG-0.
Safety invariants verified:
- Design requires no free-form command execution, no direct Arena apply, no secret persistence, no unavailable-as-passed, no legacy retirement without gates, and no external provider calls in Local Only mode.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Known limitations:
- PFG implementation has not started.
Remaining gaps:
- PFG-1 must verify current Portal code and lock compatibility gates before Portal polish implementation.
Next package:
- PFG-1 — Portal polish audit and compatibility gates.
Blocker:
- None.
```

```text
Work package: PFG-1 — Portal polish audit and compatibility gates
Status: acceptance_complete
Changed modules/files:
- tests/test_portal_pfg1_regression_locks.py (new — behavior locks)
- docs/atlas_portal_forge_current_status.md
Audit (current Portal code vs PR-PPC-12 / UI reconciliation):
- Portal nav, web/js/portal.js, AtlasPipelineAPI Portal surface, and data
  lifecycle services verified against the live router (app/api/portal.py) and
  contracts (app/portal/contracts.py); no behavioral drift found.
- Confirmed remaining polish gaps (now the PFG-2..PFG-4/PFG-27 backlog):
  - browser/server upload import (server-path picker landed; client upload
    endpoint/UI still PFG-2);
  - snapshot-list / start-from-snapshot run selector (PFG-3);
  - legacy package manifest sidecar repair (PFG-4);
  - Forge Trace panel / Portal x Forge metadata (PFG-27).
Public contracts added or changed:
- None; tests-only. No runtime behavior changed.
Behavior locked (regression):
- Export advertises and produces data-free packages (no data/ entries).
- PortalRunRequest (StrictContractModel, extra="forbid") rejects any free-form
  command field (command/cmd/args/shell/entrypoint_override); the /api/portal/run
  route 422s an unknown command field — no free-form command execution surface.
- Untrusted imported packages are quarantined: blocked by default, allowed only
  after explicit untrusted_override_acknowledged.
- START_FROM_SNAPSHOT run mode requires a snapshot_id.
- Capabilities advertise data_management_enabled / run_enabled and expose no
  command-execution capability.
Focused tests:
- python -m pytest tests/test_portal_pfg1_regression_locks.py -> 5 passed.
Affected tests:
- python -m pytest tests/test_portal_catalog.py tests/test_portal_data_lifecycle.py
  tests/test_portal_runtime.py tests/test_portal_recovery_lifecycle.py
  tests/test_portal_import_browse.py tests/test_portal_pfg1_regression_locks.py
  -> 33 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-1 is an audit + behavior-lock package.
Safety invariants verified:
- No free-form command execution surface; quarantine of untrusted imports;
  data-free export; strict contract rejects extra fields.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-2 browser/server upload import endpoint and UI.
Next package:
- PFG-2 — Portal import upload endpoint and UI.
Blocker:
- None.
```

```text
Work package: PFG-2 — Portal import upload endpoint and UI
Status: acceptance_complete
Changed modules/files:
- app/api/portal.py (POST /api/portal/import/upload)
- app/portal/catalog.py (quarantine staging helpers; BadZipFile -> PortalCatalogError)
- web/js/atlas_pipeline_api.js (uploadPortalImport; FormData-aware atlasFetch)
- web/js/portal.js (modal upload control + trust warning; server-path picker kept)
- web/css/app.css (upload button)
- tests/test_portal_import_upload.py (new)
Public contracts added or changed:
- New endpoint POST /api/portal/import/upload (multipart). Existing path import,
  preflight, export, run contracts unchanged.
Behavior implemented:
- Browser/server upload of a Capsule .zip/.portal.zip. The upload is streamed into
  a per-import quarantine directory under a sanitized filename, capped at 100 MB
  (compressed) before open, then run through the same preflight (traversal-safe
  entry names, file-count/size/compression-ratio limits, manifest + checksum
  verification) as path import. Quarantine staging is always cleaned up.
- Unsafe paths/archives fail closed: non-archive extension -> 400
  unsupported_archive_extension; empty -> 400 empty_upload; non-zip / invalid
  capsule -> 400 (archive_not_a_zip / manifest_*); oversized -> 413.
- Imported package stays untrusted_imported_package (quarantine preserved); Run is
  still blocked until explicit acknowledgement.
- UI: mobile-friendly upload control (hidden file input + accent button) inside the
  import folder picker, with an explicit untrusted trust warning. Server-path
  developer workflow (folder picker / manual path) preserved.
Focused tests:
- python -m pytest tests/test_portal_import_upload.py -> 4 passed
  (valid upload classified untrusted + cataloged + quarantine cleaned;
   non-archive extension 400; empty 400; invalid archive fails closed + not
   cataloged + no quarantine residue).
Syntax checks:
- node --check web/js/portal.js, web/js/atlas_pipeline_api.js -> ok
- python -m py_compile app/api/portal.py app/portal/catalog.py -> ok
Affected tests:
- python -m pytest tests/test_portal_catalog.py tests/test_portal_data_lifecycle.py
  tests/test_portal_runtime.py tests/test_portal_recovery_lifecycle.py
  tests/test_portal_import_browse.py tests/test_portal_import_upload.py
  tests/test_portal_pfg1_regression_locks.py -> 37 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-2 is a Portal import-path package, no model execution.
Unavailable checks:
- Live mobile-browser upload not executed in CI; UI control uses a standard file
  input (accept=.zip,.portal.zip) which opens the native mobile picker.
- Repo-wide `pytest -k portal` collection surfaces pre-existing, unrelated
  collection errors (missing web/atlas-next fixtures, cp932 decode) in atlas vue/
  scale contract tests; not introduced by PFG-2.
Safety invariants verified:
- Quarantine staging + sanitized filename; fail-closed on unsafe archives;
  untrusted classification preserved; data-free export and no-free-form-command
  locks (PFG-1) still pass.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-3 snapshot listing and start-from-snapshot UI.
Next package:
- PFG-3 — Portal snapshot listing and start-from-snapshot UI.
Blocker:
- None.
```

```text
Work package: PFG-3 — Portal snapshot listing and start-from-snapshot UI
Status: acceptance_complete
Changed modules/files:
- app/api/portal.py (GET /api/portal/installations/{id}/snapshots)
- web/js/atlas_pipeline_api.js (listPortalSnapshots)
- web/js/portal.js (run-sheet Start-from-snapshot mode + snapshot selector;
  also fixed a stray NUL byte that had crept into the PFG-2 UPLOAD_HANDLED sentinel)
- tests/test_portal_snapshot_listing.py (new)
Public contracts added or changed:
- New endpoint GET /api/portal/installations/{installation_id}/snapshots
  returning {available, snapshots:[{snapshot_id, source, last_modified, data_bytes}]}.
  Existing run/data/snapshot-save contracts unchanged.
Behavior implemented:
- Run sheet now offers "Start from snapshot"; selecting it lazily lists the
  installation's snapshots and runs with run_mode=start_from_snapshot + snapshot_id.
- Empty-state ("スナップショットがありません") and unavailable-state ("一覧を取得
  できません") are shown truthfully; Run is blocked until a snapshot is chosen.
- Save-as-snapshot during run and discard semantics are unchanged (existing data
  lifecycle services); start-from-snapshot restore and discard remain covered by
  test_portal_data_lifecycle.
Focused tests:
- python -m pytest tests/test_portal_snapshot_listing.py -> 2 passed
  (empty list available+truthful; saved snapshots listed, isolated per installation,
   correct data_bytes).
Syntax checks:
- node --check web/js/portal.js (NUL-free), web/js/atlas_pipeline_api.js -> ok
- python -m py_compile app/api/portal.py -> ok
Affected tests:
- python -m pytest tests/test_portal_catalog.py tests/test_portal_data_lifecycle.py
  tests/test_portal_runtime.py tests/test_portal_recovery_lifecycle.py
  tests/test_portal_import_browse.py tests/test_portal_import_upload.py
  tests/test_portal_pfg1_regression_locks.py tests/test_portal_snapshot_listing.py
  -> 39 passed. START_FROM_SNAPSHOT restore + discard covered by
  test_save_as_snapshot_does_not_mutate_current_or_source_snapshot and
  test_discard_rolls_back_session_writes_and_ephemeral_defaults_to_discard.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-3 is a Portal data-lifecycle UI package.
Safety invariants verified:
- Snapshot list isolated per installation; no free-form command / data-free / quarantine
  locks (PFG-1) still pass.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-4 legacy package manifest sidecar repair.
Next package:
- PFG-4 — Legacy package manifest sidecar repair.
Blocker:
- None.
```

```text
Work package: PFG-4 — Legacy package manifest sidecar repair
Status: acceptance_complete
Changed modules/files:
- app/portal/catalog.py (repair_manifest_sidecar)
- app/api/portal.py (POST /packages/{id}/{ver}/{hash}/repair-manifest)
- web/js/atlas_pipeline_api.js (repairPortalManifest)
- web/js/portal.js (Repair manifest button on profile-less cards + handler)
- tests/test_portal_manifest_repair.py (new)
Public contracts added or changed:
- New endpoint POST /api/portal/packages/{package_id}/{version}/{content_hash}/repair-manifest
  returning {status: repaired|unrecoverable, reason?, record, manifest?}.
Behavior implemented:
- Re-projects a missing/stale manifest sidecar from the immutable package archive's
  own metadata/manifest.json; launch profiles are inferred only from package
  content + the record. The package ZIP is never mutated (only the
  {hash}.manifest.json sidecar + the record JSON's manifest_path are written).
- Recoverable legacy records regain launch profiles in the catalog after repair.
- Unrecoverable records (archive missing -> package_archive_missing; no/invalid
  manifest in archive -> manifest_unrecoverable) return a clear status and the UI
  shows a safe unavailable state ("再ビルドが必要") instead of pretending to run.
- Catalog cards with no manifest projection now show a "マニフェスト修復" button.
Focused tests:
- python -m pytest tests/test_portal_manifest_repair.py -> 3 passed
  (repair recreates sidecar + restores profiles + ZIP bytes unchanged;
   archive-missing -> unrecoverable/package_archive_missing; unknown -> 404).
Syntax checks:
- node --check web/js/portal.js (NUL-free), web/js/atlas_pipeline_api.js -> ok
- python -m py_compile app/api/portal.py app/portal/catalog.py -> ok
Affected tests:
- Portal suite (9 files) -> 42 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-4 is a Portal catalog repair package.
Safety invariants verified:
- No package archive mutation (asserted by byte-for-byte ZIP comparison);
  unrecoverable state is explicit; PFG-1 data-free / no-command / quarantine locks
  still pass.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- Portal polish track (PFG-1..PFG-4) complete. Forge core begins at PFG-5.
Next package:
- PFG-5 — Forge core schemas and taxonomies.
Blocker:
- None.
```

```text
Work package: PFG-5 — Forge core schemas and taxonomies
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/__init__.py (new package; re-exports)
- agent/model_forge/schema.py (ProviderDescriptor, ModelDescriptor, ModelProfile,
  BenchmarkPreset, ArenaCandidate + AdoptionState, CandidateScore,
  ForgeExecutionRequest, ForgeExecutionResult, ProviderSupport, ForgeUsage,
  SourceClass)
- agent/model_forge/stage_taxonomy.py (ForgeStage, StageMode, default rollout)
- agent/model_forge/route_taxonomy.py (ForgeRoute)
- agent/model_forge/source_policy.py (SourceMode, PrivacyMode, default privacy matrix)
- tests/test_model_forge_schema.py (new)
Public contracts added or changed:
- New, isolated agent/model_forge package. No existing production module imports it,
  so there is no production behavior change.
Behavior implemented:
- Pure pydantic contracts (extra="forbid") + taxonomy/enum helpers. No provider
  execution, no network, no router wiring.
- Safety defaults baked into the taxonomy: providers disabled by default; default
  stage modes are only shadow_select/disabled (changes_production_routing == False
  for every stage default); Local Only blocks external providers; unlisted stages
  default to the most restrictive privacy mode (no_external_code).
Focused tests:
- python -m pytest tests/test_model_forge_schema.py -> 13 passed
  (roundtrip for all 8 schemas; rejects unknown fields + bad enums + empty ids;
   taxonomy membership; default rollout keeps Forge off for production routing;
   source/privacy defaults safe; provider disabled by default).
Syntax checks:
- python -c "import agent.model_forge" -> imports with no side effects (31 exports).
No external calls:
- Confirmed; module set is schema/taxonomy only.
No production routing behavior change:
- Confirmed; grep shows no app/ or main.py or other agent/ module imports model_forge.
Real model / Portal / OpenRouter evidence:
- None; schemas only.
Safety invariants verified:
- Forge off by default (provider.enabled False, stage defaults non-production);
  Local Only blocks external; restrictive privacy default.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-6 provider base + registry (config + health), still no execution.
Next package:
- PFG-6 — provider base and registry.
Blocker:
- None.
```

```text
Work package: PFG-6 — provider base and registry
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/provider_base.py (ForgeProvider ABC, HealthState, ProviderHealth,
  errors, redact_for_log)
- agent/model_forge/provider_registry.py (ProviderRegistry)
- agent/model_forge/__init__.py (re-exports)
- tests/test_model_forge_provider_registry.py (new)
Public contracts added or changed:
- New provider interface + registry inside the isolated agent/model_forge package.
  Still not imported by any production module — no production behavior change.
Behavior implemented:
- ForgeProvider abstract base: execute_chat_completion (abstract), health_check,
  guard_executable, supports_contract, list_models, estimate_cost,
  redact_request_for_log. Fail-closed defaults: not-enabled -> DISABLED;
  required credential missing -> UNAVAILABLE; otherwise READY.
- ProviderRegistry: register/get/descriptors/health/health_all/ready_providers/execute.
  execute() runs only when health is READY; DISABLED/UNAVAILABLE/ERROR fail closed
  before execute_chat_completion is ever called. health() never propagates an
  exception (unexpected -> ERROR, recorded separately from UNAVAILABLE).
- redact_for_log masks credential- and source-bearing keys recursively.
Focused tests:
- python -m pytest tests/test_model_forge_provider_registry.py -> 7 passed:
  enabled local provider ready+executes; disabled provider never executed
  (executed flag stays False); missing credentials do not crash -> UNAVAILABLE,
  then READY once set; unknown provider -> ERROR not exception; health_check
  exception -> ERROR; redact masks secrets/source; ready_providers excludes
  disabled+unavailable.
- Full model_forge suite (schema + registry) -> 20 passed.
No external calls:
- Confirmed; base/registry perform no network. Concrete providers arrive in PFG-7+.
No production routing behavior change:
- Confirmed; no app/ or main.py import of model_forge.
Real model / Portal / OpenRouter evidence:
- None; interface + registry only.
Safety invariants verified:
- Disabled-by-default external providers never execute; UNAVAILABLE distinct from
  ERROR; missing credentials fail closed without crashing; secrets/source redacted
  from logs.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-7 Legacy Atlas Executor adapter (wrap existing path as a Forge provider).
Next package:
- PFG-7 — Legacy Atlas Executor adapter.
Blocker:
- None.
```

```text
Work package: PFG-7 — Legacy Atlas Executor adapter
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/providers/__init__.py (new)
- agent/model_forge/providers/legacy_atlas.py (LegacyAtlasProvider)
- agent/model_forge/__init__.py (re-exports)
- tests/test_model_forge_legacy_atlas.py (new)
Inventory of legacy model-execution callers (task 1):
- agent/atlas_llm_json_adapter.py :: AtlasLLMJsonAdapter (backend_fn(system,user)->str,
  call_openai_compatible / _post_chat / _post_chat_stream) is the structured-output
  execution path Atlas planning, patch generation, verification interpretation, and
  repair use via app.state.atlas_llm_json_fn. This is the path the adapter wraps.
Public contracts added or changed:
- New LegacyAtlasProvider inside the isolated model_forge package. NOT wired into any
  production path; legacy AtlasLLMJsonAdapter remains primary and unchanged.
Behavior implemented:
- LegacyAtlasProvider wraps a backend_fn(system,user)->str|dict|None behind the Forge
  provider interface. legacy_atlas_descriptor() is local, enabled, no credential.
  run_and_capture() returns both the ForgeExecutionResult and the raw text for shadow
  comparison; execute_chat_completion() returns the result. Backend exceptions become
  contract_valid=False + an error (no crash); empty output is an invalid contract; an
  unwired backend reports UNAVAILABLE and fails closed through the registry; an optional
  output_sink records the raw output reference.
- Forge only observes/shadows: no stage cutover, no production routing change.
Focused tests:
- python -m pytest tests/test_model_forge_legacy_atlas.py -> 7 passed
  (descriptor local/enabled/no-cred; wraps backend + contract result + usage + raw;
   unwired -> UNAVAILABLE + registry fail-closed; backend exception -> error not crash;
   empty -> invalid; output_sink ref; registry executes when ready).
- Full model_forge suite -> 27 passed.
Affected existing tests:
- python -m pytest tests/test_atlas_patch_generation_incident.py -> 11 passed
  (exercises the legacy AtlasLLMJsonAdapter path this adapter wraps; unchanged).
No production routing behavior change:
- Confirmed; grep shows no app/ or main.py import of model_forge; legacy path primary.
Real model / Portal / OpenRouter evidence:
- None; adapter contract only (backend injected via stub in tests).
Safety invariants verified:
- No cutover; legacy primary; provider fails closed when unwired; no external call.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-8 local OpenAI-compatible provider adapter.
Next package:
- PFG-8 — local OpenAI-compatible provider adapter.
Blocker:
- None.
```

```text
Work package: PFG-9 — OpenRouter configuration and secret policy
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/providers/openrouter_config.py (new)
- agent/model_forge/providers/__init__.py, agent/model_forge/__init__.py (re-exports)
- tests/test_model_forge_openrouter_config.py (new)
Public contracts added or changed:
- OpenRouterConfig + gating/header helpers in the isolated model_forge package; not
  wired into production. No live HTTP (client is PFG-10/11).
Behavior implemented:
- OpenRouterConfig holds only non-secret settings and the NAME of the key env var
  (api_key_env), never the key value, so it is safe to persist/log. The key is read
  from os.environ at use time. openrouter_descriptor() is external_cloud + disabled.
- check_openrouter_allowed gates BEFORE request construction: Local Only ->
  local_only_blocks_external; disabled -> openrouter_disabled; missing key ->
  missing_openrouter_api_key; otherwise allowed. build_openrouter_headers adds
  Authorization/HTTP-Referer/X-Title from env; redact_openrouter_headers masks the
  Authorization header. live_smoke_enabled requires FORGE_OPENROUTER_LIVE_SMOKE=1 AND
  a key.
Focused tests:
- python -m pytest tests/test_model_forge_openrouter_config.py -> 7 passed
  (disabled+external by default; key read only from env and never in model_dump_json;
   Local Only blocks before request; disabled/missing-key gated; allowed when
   enabled+keyed+external; headers carry key but redaction masks it; live smoke needs
   opt-in + key).
Safety invariants verified:
- API key never persisted (config stores env name only); logs redact secrets;
  disabled by default; Local Only blocks OpenRouter before any request.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary; no external call.
Remaining gaps:
- PFG-10 OpenRouter mock chat client (no live calls).
Next package:
- PFG-10 — OpenRouter mock chat client.
Blocker:
- None.
```

```text
Work package: PFG-11 — OpenRouter model catalog cache
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/providers/openrouter_catalog.py (new), __init__ re-exports
- tests/test_model_forge_openrouter_catalog.py (new)
Behavior implemented:
- OpenRouterCatalog fetches {base_url}/models, normalizes entries into ModelDescriptors
  (public metadata only: id, display name, context window). TTL cache (config
  catalog_cache_ttl_seconds, injectable clock); optional disk cache under
  ca_data/model_forge/catalog. On fetch failure it serves the last cache marked
  stale (offline fallback); with no cache it returns status "unavailable" (never a
  passed/fetched). HTTP transport injectable (CI offline).
Focused tests:
- python -m pytest tests/test_model_forge_openrouter_catalog.py -> 6 passed
  (fetch normalizes; TTL serves cache then force_refresh refetches; offline fallback
   serves stale cache; no-cache+failure -> unavailable; disk cache stores no secret
   even with a key in env; disk cache provides offline fallback on a new instance).
- Full model_forge suite -> 55 passed.
Safety invariants verified:
- Only public model metadata cached (no secret persisted); unavailable distinct from
  fetched/from_cache; no live call in CI.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-12 provider health + Source Mode/privacy policy selection.
Next package:
- PFG-12 — provider health and Source Mode policy.
Blocker:
- None.
```

```text
Work package: PFG-13 — benchmark preset schema and initial presets
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/benchmark_presets.py (new), __init__ re-exports
- tests/test_model_forge_benchmark_presets.py (new)
Behavior implemented:
- Built-in presets for every task family (Quick, Web App, Game/Canvas, UI/Visual,
  DB/Persistence, Repair, Greenfield), each declaring tasks, required evaluators,
  recommended routes, risk level, runtime budget, and profile dimensions.
- validate_preset enforces tasks + required_evaluators + positive runtime budget;
  load_presets surfaces only valid presets; get_preset/preset_listing provide
  API-ready data. No model execution.
Focused tests:
- python -m pytest tests/test_model_forge_benchmark_presets.py -> 5 passed
  (required Quick/Web App/Repair/Greenfield present; all builtins valid; validation
   flags missing fields; get_preset known/unknown; listing API-ready).
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-14 Arena runner foundation.
Next package:
- PFG-14 — Arena runner foundation.
Blocker:
- None.
```

```text
Work package: PFG-8 — local OpenAI-compatible provider adapter
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/providers/local_openai_compatible.py (new)
- agent/model_forge/providers/__init__.py, agent/model_forge/__init__.py (re-exports)
- tests/test_model_forge_local_openai.py (new)
Public contracts added or changed:
- New LocalOpenAICompatibleProvider in the isolated model_forge package; not wired
  into production. No production routing change.
Behavior implemented:
- Non-streaming POST {base_url}/v1/chat/completions to a local/self-hosted
  OpenAI-compatible server. source_class=self_hosted (never external_cloud), no
  credential. Injectable HTTP transport (default urllib) so CI runs offline; timeout
  and error classification (timeout / connection_error / http_<code> /
  malformed_response / empty_output). Single-model servers supported (model omitted
  when unset; result model_id falls back to the response model / provider id).
  Missing base_url -> UNAVAILABLE; disabled -> DISABLED; both fail closed via registry.
Focused tests:
- python -m pytest tests/test_model_forge_local_openai.py -> 9 passed
  (8 mock-transport tests: success+usage, http_500, timeout/connection, malformed,
   empty, missing-base-url unavailable+fail-closed, disabled; plus 1 real :8080 smoke).
- Full model_forge suite -> 36 passed.
Real local provider evidence:
- test_real_local_server_smoke ran against a live llama.cpp server on
  http://localhost:8080 (Mistral-Small-3.2-24B): a real non-streaming chat completion
  returned a contract-valid result with errors == []. Skipped automatically when no
  server is reachable (so CI makes no network call).
No external cloud assumption:
- Confirmed; self_hosted source class, no credential, local base URL only.
No production routing behavior change:
- Confirmed; no app/ or main.py import of model_forge.
Safety invariants verified:
- Disabled/unavailable fail closed; no external credential; offline by default in CI.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-9 OpenRouter configuration and secret policy (env-only key, disabled default).
Next package:
- PFG-9 — OpenRouter configuration and secret policy.
Blocker:
- None.
```

```text
Work package: PFG-10 — OpenRouter mock chat client
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/providers/openrouter_client.py (new), __init__ re-exports
- tests/test_model_forge_openrouter_client.py (new)
Behavior implemented:
- OpenRouterProvider implements non-streaming chat completions behind the provider
  interface with a bounded timeout, request/response normalization, and usage/latency/
  error capture. Endpoint is {base_url}/chat/completions; auth/referer/title headers
  come from env via build_openrouter_headers. Per-request Local Only gate blocks
  before any HTTP. Disabled config -> DISABLED, missing key -> UNAVAILABLE.
- All errors become structured results: local_only_blocks_external / timeout /
  connection_error / http_<code> / malformed_response / empty_output.
Focused tests:
- python -m pytest tests/test_model_forge_openrouter_client.py -> 6 passed
  (disabled-by-default DISABLED; enabled-no-key UNAVAILABLE; mock success normalizes
   + Bearer header + stream False + usage; Local Only blocks before any HTTP;
   timeout/http_429/malformed structured; mock-only execution).
CI / live policy:
- All tests inject a mock HTTP transport; no live API call. Live smoke remains gated
  behind FORGE_OPENROUTER_LIVE_SMOKE=1 + OPENROUTER_API_KEY (PFG-34).
Safety invariants verified:
- No live call in CI; secrets only in headers (redactable), never persisted; Local
  Only blocks OpenRouter before request; errors structured not raised.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-11 OpenRouter model catalog cache (mock + offline fallback).
Next package:
- PFG-11 — OpenRouter model catalog cache.
Blocker:
- None.
```

```text
Work package: PFG-12 — provider health and Source Mode policy
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/provider_policy.py (new), __init__ re-exports
- tests/test_model_forge_provider_policy.py (new)
Behavior implemented:
- source_class_allowed: Local Only -> local/self_hosted only; Frontier Only ->
  external only; local_preferred/hybrid/frontier_preferred -> both.
- privacy_allowed_for_provider: local/self_hosted always allowed (data stays local);
  external providers must declare the requested privacy mode in privacy_capabilities.
- resolve_provider_policy / provider_availability_matrix / select_eligible_provider_ids:
  combine registry health + source mode + privacy into a ProviderPolicyDecision
  (selectable + reasons + recorded source/privacy modes + decided_at) — API-ready for
  the UI and serializable as run evidence.
Focused tests:
- python -m pytest tests/test_model_forge_provider_policy.py -> 6 passed
  (source-class rules; Local Only makes external unselectable; unsupported privacy
   blocks external; local privacy always allowed; disabled -> health reason;
   availability matrix is API-ready and records the decision).
Safety invariants verified:
- External provider cannot be selected under Local Only or an unsupported privacy
  mode; source/privacy decisions are recorded as evidence.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-13 benchmark preset schema + initial presets.
Next package:
- PFG-13 — benchmark preset schema and initial presets.
Blocker:
- None.
```

```text
Work package: PFG-14 — Arena runner foundation
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/arena_runner.py (new), __init__ re-exports
- tests/test_model_forge_arena_runner.py (new)
Behavior implemented:
- ArenaRunner executes model x route candidate specs through the provider registry in
  a non-applying mode. It checks provider policy first (Local Only / privacy block a
  candidate, which is recorded but never executed), runs selectable candidates via the
  provider interface (run_and_capture when available), and persists each candidate's
  ForgeExecutionResult metadata + raw output under ca_data/model_forge/arena_runs/.
- Every ArenaCandidate defaults to adoption_state=not_applied; the runner never mutates
  workspace source and never applies a candidate (no Safe Apply bypass). Works with or
  without a disk store.
Focused tests:
- python -m pytest tests/test_model_forge_arena_runner.py -> 3 passed
  (candidates run + not_applied + raw/metadata persisted; Local Only blocks the
   external candidate from executing and records policy_blocked; in-memory run).
Safety invariants verified:
- No source mutation; candidates stay not_applied; Arena never bypasses Safe Apply;
  external candidate not executed under Local Only.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-15 Candidate Evaluator foundation.
Next package:
- PFG-15 — Candidate Evaluator foundation.
Blocker:
- None.
```

```text
Work package: PFG-15 — Candidate Evaluator foundation
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/candidate_evaluator.py (new), __init__ re-exports
- tests/test_model_forge_candidate_evaluator.py (new)
Behavior implemented:
- CandidateEvaluator runs mechanical evaluators in the detailed-design order
  (contract parse, schema/format, syntax/static, workspace policy, focused/related
  tests, Portal runtime, requirement coverage, risk/minimality, cost/latency/privacy)
  and aggregates a CandidateScore with explicit blocked_reasons.
- Hard reject conditions short-circuit the verdict: invalid contract, malformed JSON,
  python syntax error, unrelated file edit, test deletion/weakening, public API change
  without Blueprint approval, privacy violation, unsafe runtime path, Safe Apply bypass.
- Optional evidence uses None => UNAVAILABLE, never counted as passed: an unavailable
  evaluator does not raise the score and does not satisfy a required check. No LLM judge
  is used or required; the evaluator is pure mechanics.
Focused tests:
- python -m pytest tests/test_model_forge_candidate_evaluator.py -> 8 passed
  (invalid contract rejected; malformed JSON rejected; unavailable evaluators stay
   UNAVAILABLE and only passing evaluators score; failing focused tests reject;
   unrelated edit / test deletion / safe-apply bypass / public-API hard reject;
   python syntax error rejected + valid code passes; unknown language static check
   is unavailable not passed).
- python -m pytest tests/test_model_forge_*.py -> 77 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-15 is a mechanical (non-LLM) evaluator package.
Safety invariants verified:
- unavailable distinct from passed; Arena/Safe Apply bypass is a hard reject; no LLM
  judge required; evaluator never mutates source.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-16 Model Profile Store and profile updater.
Next package:
- PFG-16 — Model Profile Store and profile updater.
Blocker:
- None.
```

```text
Work package: PFG-16 — Model Profile Store and profile updater
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/profile_store.py (new), __init__ re-exports
- tests/test_model_forge_profile_store.py (new)
Behavior implemented:
- ProfileStore persists per-(provider,model) profiles under
  ca_data/model_forge/profiles/{key}/ as an append-only observations.jsonl plus a new
  profile.vN.json on every update (earlier versions never rewritten) and a latest.json
  pointer. dimension_scores are a weighted mean recomputed purely from the observation
  log, so scores are reproducible.
- update_from_candidate_score maps a mechanical CandidateScore onto named dimensions
  (rejected -> 0.0, eligible -> final_score). record_user_feedback records user
  save/discard/Capsule decisions as weak_feedback observations that are preserved as
  evidence but EXCLUDED from scoring by default (weak_weight=0.0), so a user decision
  alone never moves a model's score.
Focused tests:
- python -m pytest tests/test_model_forge_profile_store.py -> 5 passed
  (versioned + append-only; raw evidence preserved + recomputable scores; user
   feedback weak and score-neutral; update_from_candidate_score eligible/rejected;
   per-model isolation + list_profiles).
- python -m pytest tests/test_model_forge_*.py -> 82 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-16 is a persistence/aggregation package, no model execution.
Safety invariants verified:
- append-only observation log; versioned profiles; raw evidence preserved; weak user
  feedback never moves the score on its own.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-17 Stage Matrix policy and selector.
Next package:
- PFG-17 — Stage Matrix policy and selector.
Blocker:
- None.
```

```text
Work package: PFG-17 — Stage Matrix policy and selector
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/stage_matrix.py (new), __init__ re-exports
- tests/test_model_forge_stage_matrix.py (new)
Behavior implemented:
- StageMatrix stores one StagePolicyEntry per ForgeStage (disabled/fixed_model/
  shadow_select/auto_select/arena_select/fallback_only), defaulting to the safe taxonomy
  default (disabled or shadow_select) and optionally persisting to a JSON file.
- StageSelector turns a policy + candidate pool into a StageSelection, ranking candidates
  by the stage's profile dimension via ProfileStore and recording the selection reasons.
  shadow_select/arena_select keep changes_production_routing=False and legacy primary;
  arena_select records candidate_requires_safe_apply; auto_select/fixed_model route live.
- No automatic cutover: set_policy to an active production-routing mode raises
  PermissionError unless allow_production_routing=True is passed explicitly.
Focused tests:
- python -m pytest tests/test_model_forge_stage_matrix.py -> 6 passed
  (defaults disabled/shadow only; active modes require ack; shadow does not change
   routing; disabled selects nothing with reason; auto routes after ack + persists;
   arena requires Safe Apply).
- python -m pytest tests/test_model_forge_*.py -> 88 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-17 is a policy/selection package, no model execution.
Safety invariants verified:
- no automatic cutover (explicit acknowledgement required); shadow/arena keep legacy
  primary; selection reasons always recorded and serialisable for API/UI.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-18 Route Matrix policy and selector.
Next package:
- PFG-18 — Route Matrix policy and selector.
Blocker:
- None.
```

```text
Work package: PFG-18 — Route Matrix policy and selector
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/route_matrix.py (new), __init__ re-exports
- tests/test_model_forge_route_matrix.py (new)
Behavior implemented:
- ChangeClass taxonomy (trivial/micro/small/medium/large/critical/greenfield) mapped to
  ordered candidate routes; repair-style task categories pull in repair routes.
- RouteSelector records every decision (selected_route, candidates, reasons, overridden,
  critical_gate_required, decided_at). Large/critical changes strip unsafe micro routes
  (deterministic/micro_patch/direct_patch) from the candidate set and override any
  requested unsafe micro route; critical changes always route through critical_gate.
Focused tests:
- python -m pytest tests/test_model_forge_route_matrix.py -> 7 passed
  (micro change uses micro route; large change cannot be forced through a micro route;
   critical forces critical_gate with and without a request; default route recorded;
   repair task pulls repair routes; greenfield uses skeleton route).
- python -m pytest tests/test_model_forge_*.py -> 95 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-18 is a route policy/selection package, no model execution.
Safety invariants verified:
- large/critical tasks cannot be forced through unsafe micro routes; critical_gate kept
  for critical changes; route decisions are evidence-recorded.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-19 Forge backend API.
Next package:
- PFG-19 — Forge backend API.
Blocker:
- None.
```

```text
Work package: PFG-19 — Forge backend API
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/forge_service.py (new) — ForgeService composition facade
- agent/model_forge/loadouts.py (new) — Loadout schema + 7 default loadouts + JSON store
- app/api/forge.py (new) — /api/forge router (14 endpoints)
- app/server.py — register forge_router
- agent/model_forge/__init__.py — re-exports
- tests/test_forge_api.py (new)
Public contracts added or changed:
- New /api/forge surface: GET status/providers/models/profiles/leaderboard/presets,
  POST arena/run + GET arena/runs/{id}, GET/POST stage-policy, GET/POST route-policy,
  GET/POST loadouts. Existing routes unchanged; router is additive.
Behavior implemented:
- ForgeService composes the registry (legacy/local/openrouter providers), profile store,
  stage matrix, route matrix, arena runner, presets, and loadouts against the Atlas
  ca_data root. status() reports forge_enabled (off by default) + legacy_primary + per
  provider health. providers() serialises descriptors (credential ENV NAME only, never a
  secret value). stage-policy POST returns 409 without allow_production_routing (no auto
  cutover); route-policy POST returns 400 for an unsafe micro override; arena/run records
  external candidates as not_applied and does not execute them under Local Only.
Focused tests:
- python -m pytest tests/test_forge_api.py -> 7 passed
  (status off + legacy primary; provider states visible + no secret leak; presets/models/
   profiles/leaderboard; stage cutover needs ack -> 409; unsafe route override -> 400;
   loadout defaults + custom persistence; arena Local Only blocks external).
- python -m pytest tests/test_model_forge_*.py tests/test_forge_api.py -> 102 passed.
- python -c create_app() -> 14 /api/forge routes registered; server imports cleanly.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-19 exposes the API surface, no live model execution.
Safety invariants verified:
- secrets never returned; disabled/unavailable states visible; no automatic cutover
  (409); unsafe route override refused (400); arena never auto-applies; Local Only blocks
  external.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-20 Forge top-level nav and shell UI.
Next package:
- PFG-20 — Forge top-level nav and shell UI.
Blocker:
- None.
```

```text
Work package: PFG-20 — Forge top-level nav and shell UI
Status: acceptance_complete
Changed modules/files:
- ui/index.html — Forge desktop nav button + mobile tab, forge-col shell panel, mode
  plumbing (UI_VALID_MODES/UI_PRIMARY_MODES, _FORGE_MOB_TAB_IDS, _updateMobTabs, setMode
  + mobSwitch forge branches, desktop/mobile show-hide), forge.js include.
- web/js/forge.js (new) — read-only Forge shell (window.Forge.activate/onLeave/refresh).
- web/css/app.css — forge-col/shell/card/badge styles mirroring Portal; mobile rules.
- tests/test_forge_ui_shell.py (new) — structural locks.
Behavior implemented:
- A Forge top-level mode sits between Echo/Nexus and Portal (desktop + mobile). Selecting
  Forge shows the forge-col shell and calls window.Forge.activate(), which fetches
  /api/forge/status + /providers and renders a simple Overview (Forge on/off, source mode,
  profile count) and Provider health list. Default view is intentionally minimal.
- Forge is hidden by default and never displaces Portal; Portal nav is unchanged.
Syntax checks:
- node --check web/js/forge.js -> OK; node --check web/js/portal.js -> OK (unchanged).
- inline #index.html script extracted + node --check -> OK (663k chars).
Focused tests:
- python -m pytest tests/test_forge_ui_shell.py -> 6 passed (desktop+mobile nav exist;
  shell column exists; mode plumbing knows forge; script included once; Portal nav intact;
  forge.js exposes activate and is read-only).
Unavailable checks:
- Live browser/mobile rendering not executed in CI; TestClient /static/js/forge.js 404s
  exactly like the working /static/js/portal.js (static mounted at runtime), so this is
  not a regression. Mobile viewport verified structurally (atlas-mode row collapse +
  mob-forge wiring), not via a real device.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-20 is UI shell only, no model execution.
Safety invariants verified:
- Forge shell is read-only (no execution POST); Portal Save/Snapshot/Discard/run paths
  untouched; legacy primary.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-21 Forge Overview and Provider cards (richer overview).
Next package:
- PFG-21 — Forge Overview and Provider cards.
Blocker:
- None.
```

```text
Work package: PFG-21 — Forge Overview and Provider cards
Status: acceptance_complete
Changed modules/files:
- web/js/forge.js — Overview card (Forge state, Active loadout, Source mode, profiles) +
  per-provider cards (legacy/local/OpenRouter) with health badge and a plain note.
- web/css/app.css — provider card / note styles.
- tests/test_forge_overview_render.py (new) — node-driven render test.
Behavior implemented:
- The default Forge view shows an Overview (with the active loadout name from /loadouts)
  and a Provider card per registered provider. A non-ready external provider renders a
  human note instead of error noise: OpenRouter shows "Disabled by default…" / "No API key
  configured…"; local shows "No local server configured…"; legacy shows it runs in the
  Atlas pipeline. The UI works with no configured external provider.
Syntax / render checks:
- node --check web/js/forge.js -> OK.
Focused tests:
- python -m pytest tests/test_forge_overview_render.py tests/test_forge_ui_shell.py ->
  10 passed (Overview renders with no external provider; all three providers labelled;
  missing OpenRouter key is disabled + plain note, NOT an error badge; local-without-server
  config hint). Render is driven through the real web/js/forge.js under a node DOM stub.
Unavailable checks:
- Live browser render not executed; node DOM-stub render exercises the real render path.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-21 is UI rendering only.
Safety invariants verified:
- read-only; missing external key shown as disabled/unavailable, never error spam; legacy
  primary.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-22 Skill Radar and Leaderboard UI.
Next package:
- PFG-22 — Skill Radar and Leaderboard UI.
Blocker:
- None.
```

```text
Work package: PFG-22 — Skill Radar and Leaderboard UI
Status: acceptance_complete
Changed modules/files:
- web/js/forge.js — internal tab router (Overview | Skills), Skills view (champion cards
  from /leaderboard, per-model score bars from /profiles), model detail drawer.
- web/css/app.css — forge tab, champion grid, score bar, model row, and drawer styles.
- tests/test_forge_skills_render.py (new).
Behavior implemented:
- Forge now has an internal tab strip. The Skills tab shows a Champions grid (best model
  per dimension) and a compact Models list with per-model overall score bars; clicking a
  model opens a detail drawer with all dimension scores. Empty profiles render a useful
  empty state ("No model profiles yet…"). Score bars render compactly for mobile.
Syntax / render checks:
- node --check web/js/forge.js -> OK.
Focused tests:
- python -m pytest tests/test_forge_skills_render.py tests/test_forge_overview_render.py
  tests/test_forge_ui_shell.py -> 12 passed (empty state; champions + models render with
  width-scaled bars; model rows carry a data-model key for the drawer). Skills HTML is
  built by the real web/js/forge.js under a node DOM stub.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-22 is UI rendering only and never proves model quality.
Safety invariants verified:
- read-only; no execution; empty/unavailable states truthful.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-23 Benchmark Preset selector UI.
Next package:
- PFG-23 — Benchmark Preset selector UI.
Blocker:
- None.
```

```text
Work package: PFG-23 — Benchmark Preset selector UI
Status: acceptance_complete
Changed modules/files:
- web/js/forge.js — Benchmark tab: primary preset checkboxes (Quick/Web App/Repair/
  Greenfield) + "More presets" disclosure, depth segmented control (quick/standard/deep),
  provider select + model input, external-provider policy warning, Run button that posts
  /arena/run (which never auto-applies).
- web/css/app.css — benchmark form/segment/warning/run-button styles.
- tests/test_forge_benchmark_render.py (new).
Behavior implemented:
- The Benchmark tab lets the user pick presets, depth (default standard — full/deep is
  opt-in, never forced), and a provider+model. Selecting an external provider shows a
  source/privacy policy warning. Run is disabled until preset+provider+model are chosen;
  when run it goes through /arena/run, so a candidate is recorded as not_applied and
  adoption still requires Safe Apply.
Syntax / render checks:
- node --check web/js/forge.js -> OK.
Focused tests:
- python -m pytest tests/test_forge_benchmark_render.py -> 4 passed (primary presets as
  checkboxes + More disclosure; depth defaults to standard not deep; external provider
  policy warning; Run disabled until preset+provider+model chosen).
- python -m pytest tests/test_forge_*render.py tests/test_forge_ui_shell.py
  tests/test_forge_api.py -> 23 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-23 is selector UI; any run goes through the non-applying Arena path.
Safety invariants verified:
- full/deep not forced; external provider warned + blocked under Local Only by backend;
  benchmark run never adopts a candidate (Safe Apply required).
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-24 Arena UI.
Next package:
- PFG-24 — Arena UI.
Blocker:
- None.
```

```text
Work package: PFG-24 — Arena UI
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/forge_service.py — get_arena_run now enriches each candidate with its
  persisted result metadata (contract_valid, latency_ms, errors, usage).
- web/js/forge.js — Arena tab: candidate rows (model/route/contract/latency/risk/cost),
  mechanical winner indication, and an Adoption card that requires Safe Apply.
- web/css/app.css — candidate row + adoption card styles.
- tests/test_forge_arena_ui.py (new).
Behavior implemented:
- The Arena tab shows the candidates from the last run side by side with contract pass/
  fail and latency; the winner is the contract-valid candidate with the lowest latency
  (no winner if none are valid). The Adoption card states adoption goes through Proposal →
  Safe Apply → Verification and the only button is disabled — there is NO direct apply.
Focused tests:
- python -m pytest tests/test_forge_arena_ui.py -> 3 passed (backend enriches candidates +
  candidate stays not_applied; empty state; candidates+winner render and adoption is
  Safe-Apply-only with no enabled apply button).
- python -m pytest tests/test_forge_*.py tests/test_model_forge_*.py -> 121 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-24 is UI + a read-only metadata enrichment.
Safety invariants verified:
- no direct apply button; adoption requires Safe Apply; candidates stay not_applied;
  winner is mechanical, not a model claim.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-25 Stage Matrix and Route Matrix UI.
Next package:
- PFG-25 — Stage Matrix and Route Matrix UI.
Blocker:
- None.
```

```text
Work package: PFG-25 — Stage Matrix and Route Matrix UI
Status: acceptance_complete
Changed modules/files:
- web/js/forge.js — Advanced tab with collapsible Stage Matrix (stage / mode select /
  model / reason) and Route Matrix (change class / candidate routes / critical gate),
  both hidden by default; stage mode change confirms + acknowledges live-routing modes.
- web/css/app.css — matrix row + warning pill + Advanced disclosure styles.
- tests/test_forge_matrix_ui.py (new).
Behavior implemented:
- The Advanced tab keeps both matrices inside closed <details> so they do not clutter
  normal use. Each stage row shows its current mode (preselected) and reason; a live-
  routing mode (fixed/auto/arena) shows a "routes live" warning pill. Each route row shows
  candidate routes; a critical change class shows a "critical gate" pill. Changing a stage
  to a live-routing mode requires a confirm() and posts allow_production_routing=true.
Syntax / render checks:
- node --check web/js/forge.js -> OK.
Focused tests:
- python -m pytest tests/test_forge_matrix_ui.py -> 3 passed (matrices collapsible + closed
  by default; current mode shown + live-routing warned; route matrix marks critical_gate).
- python -m pytest tests/test_forge_*.py -> 29 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-25 is advanced policy UI.
Safety invariants verified:
- advanced controls hidden by default; live-routing change confirmed + acknowledged;
  unsafe change classes flagged; current mode understandable at a glance.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-26 Loadouts UI and persistence.
Next package:
- PFG-26 — Loadouts UI and persistence.
Blocker:
- None.
```

```text
Work package: PFG-26 — Loadouts UI and persistence
Status: acceptance_complete
Changed modules/files:
- agent/model_forge/forge_service.py — apply_loadout (updates stage policy, records active
  loadout; risky loadout requires acknowledge_risky), active_loadout, status.active_loadout,
  loadouts now carry an "active" flag.
- agent/model_forge/loadouts.py — safe stage_overrides for Local Safe + Repair Specialist.
- app/api/forge.py — POST /loadouts/{id}/apply (409 risky, 404 unknown).
- web/js/forge.js — Loadouts tab (cards + Apply, active marker, risky confirm); Overview
  active-loadout uses the persisted active loadout.
- web/css/app.css — loadout card styles.
- tests/test_forge_loadouts.py (new).
Behavior implemented:
- The Loadouts tab lists the 7 builtin loadouts (+ custom). Applying a loadout writes its
  stage overrides into the stage matrix and records it active; the Overview and status
  reflect the active loadout. A risky loadout (external/live routing) requires a confirm()
  and acknowledge_risky=true (backend 409 without it).
Focused tests:
- python -m pytest tests/test_forge_loadouts.py -> 5 passed (7 defaults; safe apply updates
  stage policy + marks active; risky needs ack -> 409 then 200; unknown -> 404; cards render
  active + risky).
- python -m pytest tests/test_forge_*.py tests/test_model_forge_*.py -> 129 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-26 is loadout policy UI + persistence.
Safety invariants verified:
- risky loadout requires explicit confirmation; safe loadouts apply only non-live stage
  modes; active loadout persisted and surfaced.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-27 Portal Run Forge Trace metadata.
Next package:
- PFG-27 — Portal Run Forge Trace metadata.
Blocker:
- None.
```

```text
Work package: PFG-27 — Portal Run Forge Trace metadata
Status: acceptance_complete
Changed modules/files:
- app/portal/contracts.py — PortalForgeTrace (optional, sidecar; all fields but
  installation_id optional).
- app/portal/forge_trace.py (new) — write/read the sidecar at installation_root/
  forge_trace.json (outside package + data trees).
- app/api/portal.py — GET/POST /installations/{id}/forge-trace.
- web/js/portal.js — loadForgeTrace shows a compact trace line in the run sheet.
- ui.html — #portal-run-trace element; web/css/app.css — trace line style.
- tests/test_portal_forge_trace.py (new).
Behavior implemented:
- A Portal run can carry optional Forge provenance (provider/model/route/stage/source
  mode/arena/candidate/loadout) stored as a sidecar next to the installation. The run sheet
  shows a compact "Forge: model · route · source · loadout" line when a trace exists and
  renders nothing for legacy runs. The trace is never in the immutable package or exported
  data.
Syntax checks:
- node --check web/js/portal.js -> OK; inline ui.html script -> node --check OK.
Focused tests:
- python -m pytest tests/test_portal_forge_trace.py -> 3 passed (legacy run -> available
  false + still loads; round-trips + sidecar-safe location; per-installation isolation).
- python -m pytest tests/test_portal_forge_trace.py tests/test_portal_pfg1_regression_locks.py
  tests/test_portal_snapshot_listing.py -> 10 passed.
Real model / Portal / OpenRouter evidence:
- None claimed; PFG-27 adds optional metadata; no model executed.
Safety invariants verified:
- trace optional + sidecar-safe (not in package/data); legacy records still load;
  data-free export unchanged.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Remaining gaps:
- PFG-28 Portal evidence to Candidate Evaluator.
Next package:
- PFG-28 — Portal evidence to Candidate Evaluator.
Blocker:
- None.
```

## Update template

After each package record:

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
