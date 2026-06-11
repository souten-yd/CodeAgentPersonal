# Atlas Portal + Model Forge — Current Status

> Mutable checkpoint for Codex or Claude goal mode.
> Update this file after every coherent work package.

## Program state

- Overall: **ACTIVE — IMPLEMENTATION READY**
- Active track: `PFG-0..PFG-38`
- Current package: `PFG-8`
- Current package goal: local OpenAI-compatible provider adapter.
- Next action: add a local OpenAI-compatible provider (e.g. llama.cpp / LM Studio /
  vLLM server) behind the PFG-6 provider interface; local source class, no external
  credential, still shadow-only (no cutover).
- Last completed: `PFG-7` (Legacy Atlas Executor adapter) — acceptance_complete; see
  PFG-7 evidence below. PFG-1..PFG-6 also complete.
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
| PFG-8 | local OpenAI-compatible provider adapter | not_started |
| PFG-9 | OpenRouter configuration and secret policy | not_started |
| PFG-10 | OpenRouter mock chat client | not_started |
| PFG-11 | OpenRouter model catalog cache | not_started |
| PFG-12 | provider health and Source Mode policy | not_started |
| PFG-13 | benchmark preset schema and initial presets | not_started |
| PFG-14 | Arena runner foundation | not_started |
| PFG-15 | Candidate Evaluator foundation | not_started |
| PFG-16 | Model Profile Store and profile updater | not_started |
| PFG-17 | Stage Matrix policy and selector | not_started |
| PFG-18 | Route Matrix policy and selector | not_started |
| PFG-19 | Forge backend API | not_started |
| PFG-20 | Forge top-level nav and shell UI | not_started |
| PFG-21 | Forge Overview and Provider cards | not_started |
| PFG-22 | Skill Radar and Leaderboard UI | not_started |
| PFG-23 | Benchmark Preset selector UI | not_started |
| PFG-24 | Arena UI | not_started |
| PFG-25 | Stage Matrix and Route Matrix UI | not_started |
| PFG-26 | Loadouts UI and persistence | not_started |
| PFG-27 | Portal Run Forge Trace metadata | not_started |
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
