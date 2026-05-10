# PR4.54: Echo/ASR/TTS runtime boundary inventory and safe service seams

## Scope and guardrails

This document records PR4.53 Nexus residue cleanup and route ownership verification after PR4.52 Nexus write/research/ingest route movement, building on PR4.42 system status, PR4.43 project read-only router work, PR4.44 job read-only status extraction, PR4.45 settings ownership hardening, PR4.46 Nexus read-only status/list extraction, PR4.47 Echo read-only status/session extraction, PR4.48 lightweight runtime write-control endpoint extraction, PR4.49 job execution runtime extraction; job execution runtime extracted, PR4.50 job submit route ownership, and PR4.51 Nexus execution service extraction. Nexus execution runtime extracted into `app/services/nexus_execution.py`; PR4.52 moved Nexus write/research/ingest route ownership to `app/api/nexus.py`. PR4.50 moved `POST /jobs/submit` route ownership to `app/api/jobs.py`; job execution runtime remains in `app/services/jobs.py`, and main.py keeps only the `job_submit_provider` dependency assembly for production `main.app`.

Hard guardrails retained for this PR:

- Do not move diagnostic/heavy system endpoints such as `/system/usage/debug`.
- Do not change non-target `main.py` behavior.
- Do not change LLM inference / ASR / TTS / SBV2 / Runpod llama search behavior.
- Do not change non-target `app/api/model_settings.py`; only the targeted lightweight runtime write controls move into `app/api/runtime_controls.py`.
- Do not move settings provider implementations out of `main.py`; only route ownership belongs in `app/api/settings.py`.
- Do not remove `/settings-defaults` or the legacy `/settings/defaults` compatibility path.
- Do not place `/settings/{key}` before static defaults routes because it can shadow `/settings/defaults`.
- Do not move job execution runtime out of `app/services/jobs.py`; PR4.50 only moves `POST /jobs/submit` route ownership into `app/api/jobs.py`. PR4.51 extracts Nexus execution runtime into `app/services/nexus_execution.py`; PR4.52 moves Nexus research/ingest/write/POST route ownership into `app/api/nexus.py` without changing the execution body. Do not move Echo write/streaming runtime behavior, ASR, TTS, or UI behavior.
- Treat `KasaneCore_v2.8 == main at e94c20dfe0d23e233f4dbc817af994408e739b80` as the normal recovery baseline; PR4.52後、Nexus/Lumen/ASR/TTS/LLM are considered healthy. PR4.53 only verifies Nexus residue/ownership and must not change execution behavior.
- v2.8 health confirmation: LLM / ASR / TTS / Nexus / Lumen 正常確認済み; Runpod LLM `-ngl=999 -> OK`, `parsed_n_gpu_layers=43`, `LLM ready`, warm-up complete; ASR OK; TTS/SBV2 OK; Nexus write/research/ingest route移動後も機能OK.
- Do not change UI assets, Echo WebSocket handling, `/model/switch`, `/model/auto-load`, `/debug/llama`, or `benchmark_mem.py`.

## PR4.53 remaining `main.py` endpoint classification

- **model runtime high-risk**: `/model/auto-load`, `/model/switch`, llama lifecycle/debug endpoints including `/debug/llama`, Runpod/Linux NGL探索 endpoints/diagnostics, Windows auto-fit/model sizing, model scan/download/benchmark routes. These remain in `main.py` and are not next-move candidates.
- **audio runtime high-risk / next phase (PR4.54 inventory)**: Echo / ASR / TTS / SBV2 boundaries are documented in `docs/echo_audio_runtime_inventory.md` and represented by route-neutral helpers in `app/services/audio_runtime.py`; no routes move in PR4.54.
  - Echo read-only: already extracted to `app/api/echo.py` (`GET /echo/save-status`, `GET /echo/sessions`, `GET /echo/sessions/{filename:path}`).
  - Echo stream/write: still `main.py` high-risk (`WebSocket /echo/stream`, `DELETE /echo/sessions/{filename:path}`).
  - ASR runtime: still `main.py` high-risk for execution/load (`POST /voice/transcribe`, `POST /voice/load`); status/config moved to `app/api/audio.py` in PR4.56 with provider-backed production payloads and safe `create_app()` fallbacks.
  - TTS/SBV2 runtime: still `main.py` high-risk (`POST /tts/synthesize`, `POST /tts/synthesize-batch`, SBV2 prepare / upload routes; low-risk models and preview-normalization moved to `app/api/audio.py` in PR4.56).
  - PR4.56 moved low-risk audio read/status/config routes to `app/api/audio.py`; PR4.57 extracts the TTS/SBV2 non-streaming `/tts/synthesize` service body; PR4.58 extracts the `/tts/synthesize-batch` service body while keeping route ownership and WebSocket/Echo stream unchanged; PR4.59 extracts the SBV2 prepare service body while keeping route ownership; POST `/voice/load`, POST `/voice/transcribe`, and Echo WebSocket remain the high-risk audio execution bodies.
- **app orchestration**: Lumen/Chat execution (`/chat` and related LLM orchestration), job background execution routes still in `main.py`, and remaining project/history/files read/write/archive routes that need separate provider boundaries.
- **already extracted**: jobs router (`app/api/jobs.py`), jobs service (`app/services/jobs.py`), Nexus router owner for moved routes (`app/api/nexus.py`), Nexus execution service (`app/services/nexus_execution.py`), Echo read-only router (`app/api/echo.py`), and runtime controls router (`app/api/runtime_controls.py`).

## Legend

| Field | Meaning |
| --- | --- |
| Current owner | Module that currently owns the registered FastAPI endpoint. `main` means a direct `@app.*` route in `main.py`. |
| Kind | `read-only`, `write`, `streaming`, `websocket`, or `heavy`; combinations mean the endpoint has multiple risk factors. |
| Side effect | Expected side effect class based on route purpose; this is intentionally conservative. |
| Globals/managers/registries | Important coupling to app state, model/runtime managers, stores, registries, or filesystem. |
| create_app fallback | Whether the existing lightweight app factory can safely expose a provider-less fallback today. |
| Next move? | Whether a near-term router extraction is recommended. |
| Move ban | Whether this route should remain frozen for now. |

## A. Already moved / out of scope

These routes are already router-owned after PR4.42. If the PR4.42 system status routes appear as direct `main.py` decorators again, that is a regression.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health` | `app.api.system_status` | read-only | none | optional health provider | yes | moved in PR4.42 | yes |
| GET | `/system/readiness` | `system_readiness_api` | `app.api.system` | read-only | none | optional providers | yes | already moved | yes in PR4.41 |
| GET | `/system/summary` | `system_summary` | `app.api.system_status` | read-only | none | optional summary provider | yes | moved in PR4.42 | yes |
| GET | `/system/usage` | `system_usage` | `app.api.system_status` | read-only | live/light probe possible only through production provider | optional usage provider | yes, no probe | moved in PR4.42 | yes |
| GET | `/system/usage/debug` | `system_usage_debug_payload` | `main` | read-only / diagnostic | debug probe | usage diagnostics/provider | no factory route | intentionally left in `main.py` | yes |
| GET | `/system/env` | `system_env_api` | `app.api.system` | read-only | none | environment detection | yes | already moved | yes |
| GET | `/settings-defaults` | `get_settings_defaults_api` | `app.api.settings` | read-only | none | optional settings provider | yes | already moved | yes |
| GET | `/settings` | `get_settings_api` | `app.api.settings` | read-only | none | optional settings provider | yes | already moved | yes |
| POST | `/settings` | `save_settings_api` | `app.api.settings` | write | settings persistence through provider | optional settings provider | fallback echo only | do not expand in this PR | yes |
| GET | `/settings/defaults` | `get_settings_defaults_legacy_api` | `app.api.settings` | read-only | none | optional settings provider | yes | already moved | yes |
| GET | `/settings/{key}` | `get_setting_api` | `app.api.settings` | read-only | none | optional settings provider | yes | already moved | yes |
| PUT | `/settings/{key}` | `set_setting_api` | `app.api.settings` | write | setting persistence through provider | optional settings provider | fallback echo only | do not expand in this PR | yes |
| GET | `/models/orchestration` | `get_model_orchestration_api` | `app.api.model_settings` | read-only | none | model settings provider | yes | already moved | yes |
| POST | `/models/orchestration` | `save_model_orchestration_api` | `main` | write | persists orchestration settings | model DB/settings globals | no | not next | yes |
| GET | `/models/roles` | `get_model_role_assignments_api` | `app.api.model_settings` | read-only | none | model settings provider | yes | already moved | yes |
| POST | `/models/roles` | `save_model_role_assignments_api` | `main` | write | persists role assignments | model DB/settings globals | no | not next | yes |
| GET | `/models/db` | `list_models_db_api` | `app.api.model_settings` | read-only | none | model DB provider | yes | already moved | yes |
| GET | `/models/db/status` | `get_model_db_status_api` | `app.api.model_settings` | read-only | none | model DB provider | yes | already moved | yes |
| GET | `/model/status` | `get_model_manager_status_api` | `app.api.model_settings` | read-only | none | model manager provider | yes | already moved | yes |
| GET | `/llm/ctx` | `get_runtime_llm_ctx_api` | `app.api.runtime_controls` | read-only | none | runtime provider | yes | already moved | yes |
| POST | `/llm/ctx` | `set_runtime_llm_ctx_api` | `app.api.runtime_controls` | lightweight write | provider mutates runtime context setting in production; fallback echoes | runtime write provider | yes | moved in PR4.48 | yes |
| GET | `/llm/props` | `get_runtime_llm_props_api` | `app.api.runtime_controls` | read-only / diagnostic | may inspect runtime | runtime provider | yes | already moved | yes |
| GET | `/search/status` | `get_search_status_api` | `app.api.runtime_controls` | read-only | none | runtime provider | yes | already moved | yes |
| POST | `/search/num` | `set_search_num_api` | `app.api.runtime_controls` | lightweight write | provider mutates search count in production; fallback echoes | runtime write provider | yes | moved in PR4.48 | yes |
| POST | `/search/enable` | `enable_search_api` | `app.api.runtime_controls` | lightweight write | provider mutates search flag in production; fallback echoes | runtime write provider | yes | moved in PR4.48 | yes |
| POST | `/search/disable` | `disable_search_api` | `app.api.runtime_controls` | lightweight write | provider mutates search flag in production; fallback echoes | runtime write provider | yes | moved in PR4.48 | yes |
| GET | `/streaming/status` | `get_streaming_status_api` | `app.api.runtime_controls` | read-only | none | runtime provider | yes | already moved | yes |
| POST | `/streaming/enable` | `enable_streaming_api` | `app.api.runtime_controls` | lightweight write | provider mutates streaming flag in production; fallback echoes | runtime write provider | yes | moved in PR4.48 | yes |
| POST | `/streaming/disable` | `disable_streaming_api` | `app.api.runtime_controls` | lightweight write | provider mutates streaming flag in production; fallback echoes | runtime write provider | yes | moved in PR4.48 | yes |
| GET | `/runtime/cuda-debug` | `get_runtime_cuda_debug_api` | `app.api.runtime_controls` | read-only / diagnostic | runtime diagnostics | runtime provider | yes | already moved | yes |
| GET | `/audio/runtime/debug` | `get_audio_runtime_debug_api` | `app.api.audio` | read-only / diagnostic | audio runtime diagnostics | audio providers/registries | yes | moved in PR4.56 | yes |
| GET | `/debug/model-startup` | `get_model_startup_debug_api` | `app.api.runtime_controls` | read-only / diagnostic | reads startup diagnostics | model manager provider | yes | already moved | yes |
| `/nexus/*` | all Nexus API routes | `nexus_router` handlers | `app.nexus.router` and subrouters mounted by `main.py` | mixed read/write/heavy | research jobs, reports, exports | Nexus stores/services | no | no new split in PR4.41 | yes |
| `/static/*` | static files | Starlette static mount | `app.server.configure_static_assets` called by `main.py` | static | serves files | `WEB_DIR` | yes when directory provided | not next | yes |
| `/favicon` | browser favicon request | covered by static/UI assets when present | static mount / UI assets | static | serves files | static dirs | yes when asset exists | not next | yes |

## B. System read-only status after PR4.42

PR4.42 moved the low-risk system read-only endpoints into `app/api/system_status.py`. Production `main.app` keeps the existing provider-backed response shapes, while `create_app()` returns conservative fallback payloads without live GPU, llama, ASR, TTS, runtime, or model-manager probes. `/system/usage/debug` is diagnostic-oriented and intentionally remains a direct `main.py` route.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health` | `app.api.system_status` | read-only | none | optional health provider | yes | moved in PR4.42 | yes |
| GET | `/system/summary` | `system_summary` | `app.api.system_status` | read-only | none | provider-backed status | yes | moved in PR4.42 | yes |
| GET | `/system/usage` | `system_usage` | `app.api.system_status` | read-only | light usage probe only via production provider | provider-backed system usage | yes, fallback does not probe | moved in PR4.42 | yes |
| GET | `/system/usage/debug` | `system_usage_debug_payload` | `main` | read-only / diagnostic | debug probe | provider-backed debug details | no factory route | diagnostic; keep in `main.py` | yes |

## C. Settings candidates

Settings API ownership is complete as of PR4.45. The route owner is `app/api/settings.py`; `main.py` keeps only provider implementations registered on `app.state` for production persistence/runtime behavior. `/settings-defaults` is the unshadowed defaults alias, `/settings/defaults` is the legacy compatibility path, and both static defaults routes must remain registered before `/settings/{key}` to prevent route shadowing. Factory-created apps use conservative fallback payloads; fallback writes echo the request without database or runtime side effects.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/settings` | `get_settings_api` | `app.api.settings` | read-only | none | settings_get_all_provider or fallback map | yes | ownership complete in PR4.45 | yes |
| POST | `/settings` | `save_settings_api` | `app.api.settings` | write | persists settings only through production provider | settings_bulk_save_provider/database | fallback echo only, no DB/runtime side effect | ownership complete in PR4.45 | yes |
| GET | `/settings-defaults` | `get_settings_defaults_api` | `app.api.settings` | read-only | none | settings_defaults_provider or fallback map | yes | unshadowed defaults alias; ownership complete in PR4.45 | yes |
| GET | `/settings/defaults` | `get_settings_defaults_legacy_api` | `app.api.settings` | read-only | none | settings_defaults_provider or fallback map | yes | legacy compatibility path; must precede `/settings/{key}` | yes |
| GET | `/settings/{key}` | `get_setting_api` | `app.api.settings` | read-only | none | settings_get_provider or fallback single-key payload | yes | ownership complete in PR4.45; must follow static defaults routes | yes |
| PUT | `/settings/{key}` | `set_setting_api` | `app.api.settings` | write | persists one setting only through production provider | settings_set_provider/database | fallback echo only, no DB/runtime side effect | ownership complete in PR4.45 | yes |

## D. Project / file / job candidates

PR4.43 moved the low-risk project read-only list/history/file endpoints to `app.api.projects`. PR4.44 moved the job read-only status endpoints `GET /projects/{project}/jobs` and `GET /jobs/{job_id}/poll` to `app.api.jobs` with provider-backed production payloads and lightweight `create_app()` fallbacks. PR4.49 extracted the job execution runtime into `app/services/jobs.py`. PR4.50 moved `POST /jobs/submit` route ownership to `app/api/jobs.py`; the router delegates production submits through `app.state.job_submit_provider`, and main.py keeps only the `job_submit_provider` dependency assembly that calls `submit_job_service`.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/projects` | `get_projects_api` | `app.api.projects` | read-only | lists projects through provider | provider-backed workspace scan on `main.app` | yes: `{"projects": []}` | moved in PR4.43 | no |
| POST | `/projects` | `create_project` | `main` | write | creates project | workspace/project filesystem | no | not next | yes |
| DELETE | `/projects/{name}` | `delete_project` | `main` | write | deletes project | workspace/project filesystem | no | not next | yes |
| GET | `/projects/{project}/files` | `get_project_files_api` | `app.api.projects` | read-only | lists files through provider | provider-backed project filesystem on `main.app` | yes: empty file list | moved in PR4.43 | no |
| DELETE | `/projects/{name}/files/{path:path}` | `delete_project_file` | `main` | write | deletes file | project filesystem | no | not next | yes |
| GET | `/projects/{name}/files/{path:path}/download` | `download_project_file` | `main` | read-only / file response | serves project file | project filesystem | no | later, after list/history | yes for now |
| GET | `/projects/{name}/download` | `download_project` | `main` | read-only / heavy | zips/serves project | project filesystem/archive | no | later | yes |
| GET | `/projects/{project}/history` | `get_project_history_api` | `app.api.projects` | read-only | reads project history through provider | provider-backed project DB on `main.app` | yes: empty sessions | moved in PR4.43 | no |
| GET | `/projects/{project}/jobs` | `get_project_jobs_api` | `app.api.jobs` | read-only | lists job metadata through provider | provider-backed job registry/store on `main.app` | yes: `{"jobs": []}` | moved in PR4.44 | no |
| POST | `/jobs/submit` | `submit_job_api` | `app.api.jobs` | write / heavy / runtime execution in production provider | starts background job execution only through `main.py` `job_submit_provider` and `app/services/jobs.py`; `create_app()` fallback starts nothing | provider-backed job manager, LLM/runtime globals passed as service dependencies | yes: unavailable payload, no side effects | moved in PR4.50 | no |
| GET | `/jobs/{job_id}` | `get_job` | `main` | read-only | reads job state | job registry/store | no | later, separate from PR4.44 poll/list move | yes |
| GET | `/jobs/{job_id}/poll` | `get_job_poll_api` | `app.api.jobs` | read-only / polling | reads job state through provider | provider-backed job registry/store on `main.app` | yes: empty done poll payload | moved in PR4.44 | no |
| GET | `/jobs/{job_id}/stream` | `stream_job` | `main` | streaming | streams job events/logs | job registry/streaming response | no | PR4.44+ after non-streaming jobs | yes |
| POST | `/jobs/{job_id}/respond` | `respond_to_job` | `main` | write | sends response to active job | job manager/queues | no | PR4.44+ | yes |
| GET | `/jobs/{job_id}/logs` | `get_job_logs_api` | `main` | read-only | reads logs | job log filesystem | no | PR4.44+ | yes |
| POST | `/jobs/{job_id}/analyze_skills` | `analyze_job_for_skills` | `main` | write / heavy | launches skill analysis | job manager/LLM/skills | no | PR4.44+ | yes |

## E. Nexus candidates

PR4.46 moved the low-to-medium-risk Nexus read-only status/list endpoints into `app/api/nexus.py`. Production `main.app` registers read providers on `app.state` to preserve the existing response shapes. `create_app()` serves lightweight fallbacks that do not touch the Nexus DB, filesystem, index, LLM, SearXNG process/network, job registry, or background execution. PR4.51 extracted Nexus execution runtime into `app/services/nexus_execution.py` for research, web search, ingest/upload delegation, source/evidence execution, and report-generation boundaries. PR4.52 moved Nexus write/research/ingest route ownership to `app/api/nexus.py`; Nexus execution runtime remains in `app/services/nexus_execution.py`, and main.py keeps only Nexus provider dependency assembly. Remaining `app.nexus.router` / subrouter endpoints are document delete/download/detail, research readbacks, source file/chunk readbacks, news/market MVP, watchlists, export, and read/report subrouter endpoints that were intentionally left out of PR4.52.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/nexus/summary` | `get_nexus_summary_api` | `app.api.nexus` | read-only | none through fallback; production reads Nexus DB/job status | app-state summary provider | yes, no DB/filesystem/LLM/SearXNG/job execution touch | moved in PR4.46 | yes |
| GET | `/nexus/documents` | `get_nexus_documents_api` | `app.api.nexus` | read-only / list | none through fallback; production reads Nexus DB | app-state documents provider | yes, empty list without filesystem/index scan | moved in PR4.46 | yes |
| GET | `/nexus/jobs/active` | `get_nexus_active_jobs_api` | `app.api.nexus` | read-only / status | none through fallback; production reads Nexus active job list | app-state active jobs provider | yes, empty list without registry/background access | moved in PR4.46 | yes |
| GET | `/nexus/web/status` | `get_nexus_web_status_api` | `app.api.nexus` | read-only / status | none through fallback; production may evaluate configured provider status | app-state web status provider | yes, conservative unavailable status without SearXNG/network probe | moved in PR4.46 | yes |
| POST | `/nexus/upload`, `/nexus/search`, `/nexus/web/search`, `/nexus/web/research`, `/nexus/research/run`, `/nexus/sources/search`, `/nexus/evidence/add-from-chunks`, `/nexus/research/jobs/{job_id}/followup`, `/nexus/web/collect`, `/nexus/ask`, `/nexus/report/build` | `*_api` handlers | `app.api.nexus` | write / heavy / research / ingest | provider starts production work only on `main.app`; `create_app()` starts nothing | `app/services/nexus_execution.py` via production providers | yes, unavailable payloads | moved in PR4.52 | no |
| mixed | `/nexus/*` remaining routes | remaining Nexus API routes | `app.nexus.router` / subrouters | read/write not in PR4.52 | document delete/download/detail, research readbacks, source files/chunks, news/market MVP, watchlists, export/report reads | Nexus stores/subrouters | no | later cleanup/inventory | yes for now |

## F. Echo / audio candidates

Echo, voice, ASR, and TTS routes are high-risk because they touch streaming, WebSocket state, audio runtimes, uploaded files, model loading, and synthesis workers.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/voice/status` | `voice_status_api` | `app.api.audio` | read-only | provider-backed ASR state in production; safe fallback in create_app | voice/ASR globals via provider | yes | moved in PR4.56 | yes |
| POST | `/voice/load` | `voice_load_api` | `main` | write / heavy | loads ASR model | ASR runtime manager | no | later | yes |
| POST | `/voice/unload` | `voice_unload_api` | `main` | write / heavy | unloads ASR model | ASR runtime manager | no | later | yes |
| POST | `/voice/transcribe` | `voice_transcribe_api` | `main` | write / heavy | transcribes audio | ASR runtime/files | no | later | yes |
| GET | `/asr/config` | `asr_config_api` | `app.api.audio` | read-only | provider-backed ASR config in production; safe fallback in create_app | ASR settings/runtime via provider | yes | moved in PR4.56 | yes |
| GET | `/asr/status` | `asr_status_api` | `main` | read-only | reads ASR status | ASR runtime | no | later | yes |
| POST | `/asr/load` | `asr_load_api` | `main` | write / heavy | loads ASR engine | ASR runtime | no | later | yes |
| POST | `/asr/unload` | `asr_unload_api` | `main` | write / heavy | unloads ASR engine | ASR runtime | no | later | yes |
| GET | `/echo/save-status` | `get_echo_save_status_api` | `app.api.echo` | read-only | none through fallback; production reads save/minutes state | app-state Echo save-status provider | yes, no filesystem/audio/runtime scan | moved in PR4.47 | yes |
| GET | `/echo/runtime-status` | `echo_runtime_status` | `main` | read-only | reads runtime state | Echo/audio runtime | no | later | yes |
| WEBSOCKET | `/echo/stream` | `echo_stream_ws` | `main` | websocket / streaming | bidirectional audio session | Echo session/runtime managers | no | not until dedicated WebSocket PR | yes |
| GET | `/debug/echo` | `debug_echo` | `main` | read-only / diagnostic | reads diagnostics | Echo runtime/files | no | later | yes |
| GET | `/debu/echo` | `debug_echo_typo_redirect` | `main` | read-only | compatibility redirect/payload | Echo debug path | no | later | yes |
| POST | `/echo/generate-minutes` | `echo_generate_minutes` | `main` | write / heavy | generates minutes | Echo, LLM, files | no | later | yes |
| POST | `/echo/import-audio-transcript` | `echo_import_audio_transcript` | `main` | write / heavy | imports transcript/audio metadata | Echo files/stores | no | later | yes |
| GET | `/echo/sessions` | `get_echo_sessions_api` | `app.api.echo` | read-only | none through fallback; production lists EchoVault files | app-state Echo sessions provider | yes, empty list without filesystem/audio access | moved in PR4.47 | yes |
| GET | `/echo/sessions/{filename:path}` | `get_echo_session_api` | `app.api.echo` | read-only / file response | none through fallback; production serves EchoVault file | app-state Echo session provider | yes, conservative 404 without file read | moved in PR4.47 | yes |
| DELETE | `/echo/sessions/{filename:path}` | `echo_delete_session` | `main` | write | deletes session file | Echo session filesystem | no | later | yes |
| POST | `/echo/voice-ref` | `echo_voice_ref_post` | `main` | write | uploads voice reference | Echo voice-ref storage | no | later | yes |
| GET | `/echo/voice-ref` | `echo_voice_ref_get` | `main` | read-only / file response | serves voice reference | Echo voice-ref storage | no | later | yes |
| DELETE | `/echo/voice-ref` | `echo_voice_ref_delete` | `main` | write | deletes voice reference | Echo voice-ref storage | no | later | yes |
| GET | `/tts/status` | `tts_status_api` | `main` | read-only | reads TTS state | TTS engine registry | no | later | yes |
| GET | `/debug/TTS` | `tts_debug_api` | `main` | read-only / diagnostic | reads TTS diagnostics | TTS engine registry | no | later | yes |
| GET | `/tts/voices` | `tts_voices_api` | `main` | read-only | lists voices | TTS engine registry/files | no | later | yes |
| POST | `/tts/load` | `tts_load_api` | `main` | write / heavy | loads TTS engine | TTS engine registry | no | later | yes |
| POST | `/tts/unload` | `tts_unload_api` | `main` | write / heavy | unloads TTS engine | TTS engine registry | no | later | yes |
| POST | `/tts/translate-text` | `tts_translate_text_api` | `main` | write / heavy | translates text | TTS/translation runtime | no | later | yes |
| GET | `/api/tts/engines` | `api_tts_engines` | `main` | read-only | lists engines | TTS registry | no | later | yes |
| POST | `/api/tts/style-bert-vits2/prepare` | `api_style_bert_vits2_prepare` | `main` | write / heavy | prepares SBV2 runtime via extracted service body | injected SBV2 prepare/runtime helpers in `run_sbv2_prepare_service_body()` | no | PR4.59 service-body extracted; route later | yes |
| GET | `/api/tts/style-bert-vits2/models` | `api_style_bert_vits2_models` | `app.api.audio` | read-only | provider-backed SBV2 model list; empty safe fallback | SBV2 filesystem via provider | yes | moved in PR4.56 | yes |
| POST | `/api/tts/style-bert-vits2/preview-normalization` | `api_style_bert_vits2_preview_normalization` | `app.api.audio` | read-preview | provider-backed normalization; no-op safe fallback with no LLM call | SBV2/text processing via provider | yes | moved in PR4.56 | yes |
| POST | `/api/tts/style-bert-vits2/models/upload` | `api_style_bert_vits2_models_upload` | `main` | write / heavy | uploads model files | SBV2 filesystem | no | later | yes |
| POST | `/tts/ref-audio/upload` | `tts_ref_audio_upload` | `main` | write | uploads reference audio | TTS ref-audio filesystem | no | later | yes |
| GET | `/tts/ref-audio/list` | `tts_ref_audio_list` | `main` | read-only | lists reference audio | TTS ref-audio filesystem | no | later | yes |
| DELETE | `/tts/ref-audio/{filename}` | `tts_ref_audio_delete` | `main` | write | deletes reference audio | TTS ref-audio filesystem | no | later | yes |
| POST | `/tts/synthesize` | `tts_synthesize_api` | `main` | write / heavy | synthesizes audio via extracted service body | TTS engine registry/runtime injected into `run_tts_synthesize_service_body()` | no | PR4.57 service-body extracted; route later | yes |
| POST | `/tts/synthesize-batch` | `tts_synthesize_batch_api` | `main` | write / heavy | batch synthesis via extracted service body | TTS engine registry/runtime injected into `run_tts_synthesize_batch_service_body()` | no | PR4.58 service-body extracted; route later | yes |

## G. Model write/heavy candidates

Model write/heavy endpoints stay in `main.py`. The previous model-settings split moved only read-only settings/status routes; loading, switching, scanning, downloading, benchmarking, and debug routes remain too risky for the next PR.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/model/switch` | `model_switch` | `main` | write / heavy | switches active model | `_model_manager`, runtime settings | no | not next | yes |
| POST | `/model/auto-load` | `model_auto_load` | `main` | write / heavy | autoloads model | `_model_manager`, model DB | no | not next | yes |
| POST | `/models/db` | `add_model_db_api` | `main` | write | creates DB model row | model DB | no | later | yes |
| PUT | `/models/db/{mid}` | `update_model_db_api` | `main` | write | updates DB model row | model DB | no | later | yes |
| DELETE | `/models/db/{mid}` | `delete_model_db_api` | `main` | write | deletes DB model row | model DB | no | later | yes |
| GET | `/models/hardware` | `model_hardware_api` | `main` | read-only / diagnostic | hardware probe | GPU/runtime helpers | no | later | yes |
| GET | `/models/gguf/search` | `search_gguf_models_api` | `main` | read-only / heavy | remote/local search | Runpod/llama search helpers | no | not next | yes |
| POST | `/models/gguf/download` | `download_gguf_api` | `main` | write / heavy | downloads model | download manager/filesystem | no | later | yes |
| GET | `/models/gguf/download/status` | `gguf_download_status_api` | `main` | read-only | reads download status | download manager | no | later with download | yes |
| POST | `/models/db/scan` | `scan_model_folder_api` | `main` | write / heavy | scans model folders | model DB/filesystem | no | not next | yes |
| GET | `/models/db/scan/status` | `model_scan_status_api` | `main` | read-only / polling | reads scan status | scan registry | no | later with scan | yes |
| POST | `/models/db/benchmark/{mid}` | `benchmark_model_api` | `main` | write / heavy | benchmarks model | model manager/benchmark runner | no | not next | yes |
| POST | `/models/db/toggle/{mid}` | `toggle_model_enabled` | `main` | write | toggles model enabled | model DB | no | later | yes |
| POST | `/models/db/toggle_vlm/{mid}` | `toggle_model_vlm_enabled` | `main` | write | toggles VLM enabled | model DB | no | later | yes |
| GET | `/ensemble/settings` | `get_ensemble_settings_api` | `main` | read-only | reads ensemble config | settings/model orchestration | no | later | yes |
| POST | `/ensemble/settings` | `save_ensemble_settings_api` | `main` | write | saves ensemble config | settings/model orchestration | no | later | yes |
| GET | `/ensemble/vram` | `get_ensemble_vram_api` | `main` | read-only / diagnostic | estimates VRAM | model DB/GPU helpers | no | later | yes |
| GET | `/debug/llama` | `debug_llama` | `main` | read-only / heavy diagnostic | broad llama/runtime diagnostic | `_model_manager`, llama server, requests, filesystem | no | do not move | yes |

## H. UI/static candidates

UI routes and static mounts are not API-router candidates in the next sequence.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/` | `root` | `main` | UI/static | serves UI root | `WEB_DIR` / static files | partial | not next | yes |
| GET | `/ui` | `ui_redirect` | `main` | UI/static | redirects/serves UI route | UI/static files | partial | not next | yes |
| mount | `/static/*` | static mount | `app.server.configure_static_assets` via `main.py` | static | serves bundled web assets | `WEB_DIR` | yes if directory exists | not next | yes |
| asset | `/favicon` | static asset | static/UI assets | static | serves browser icon if present | static/UI assets | yes if asset exists | not next | yes |

## Other `main.py` route families to keep frozen

These direct `main.py` routes remain outside the immediate PR4.42/PR4.43 path. They include LLM/chat, Atlas workflow, agent, skills, git, MCP, repository, memory, and debug-test routes.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/chat` | `chat` | `main` | write / heavy | LLM chat request | LLM runtime/search/settings | no | later | yes |
| POST | `/llm/test` | `llm_test` | `main` | write / heavy | probes LLM | LLM runtime | no | later | yes |
| POST | `/plan` | `plan_only` | `main` | write / heavy | creates plan | planner/LLM runtime | no | later | yes |
| POST | `/task` | `task` | `main` | write / heavy | starts task | task runner/LLM | no | later | yes |
| POST | `/stream` | `stream` | `main` | streaming / heavy | streams task output | task runner/LLM | no | later | yes |
| POST | `/task/stream` | `task_stream` | `main` | streaming / heavy | streams task output | task runner/LLM | no | later | yes |
| POST | `/api/task/plan` | `api_task_plan` | `main` | write / heavy | creates Atlas plan | Atlas stores/LLM | no | later | yes |
| POST | `/api/atlas/autopilot/preview` | `api_atlas_autopilot_preview` | `main` | write / heavy | previews autopilot | Atlas services | no | later | yes |
| GET | `/api/atlas/autopilot/{autopilot_id}` | `api_atlas_autopilot_get` | `main` | read-only | reads autopilot | Atlas stores | no | later | yes |
| POST | `/api/atlas/autopilot/{autopilot_id}/tasks/{task_id}/plan` | `api_atlas_autopilot_task_plan` | `main` | write / heavy | creates task plan | Atlas/LLM | no | later | yes |
| POST | `/api/atlas/autopilot/{autopilot_id}/tasks/{task_id}/execution-preview` | `api_atlas_autopilot_task_execution_preview` | `main` | write / heavy | previews execution | Atlas/LLM | no | later | yes |
| GET | `/api/plans/{plan_id}` | `api_get_plan` | `main` | read-only | reads plan | Atlas stores | no | later | yes |
| GET | `/api/plans/{plan_id}/markdown` | `api_get_plan_markdown` | `main` | read-only | renders plan markdown | Atlas stores | no | later | yes |
| GET | `/api/plans/{plan_id}/approval` | `api_get_plan_approval` | `main` | read-only | reads approval | Atlas stores | no | later | yes |
| POST | `/api/plans/{plan_id}/approve` | `api_approve_plan` | `main` | write | updates approval | Atlas stores | no | later | yes |
| POST | `/api/plans/{plan_id}/request-revision` | `api_request_plan_revision` | `main` | write | records revision request | Atlas stores | no | later | yes |
| POST | `/api/plans/{plan_id}/reject` | `api_reject_plan` | `main` | write | records rejection | Atlas stores | no | later | yes |
| POST | `/api/plans/{plan_id}/execute` | `api_execute_plan` | `main` | write / heavy | starts execution | Atlas runner | no | later | yes |
| GET | `/api/atlas/runs` | `api_list_atlas_runs` | `main` | read-only | lists runs | Atlas stores | no | later | yes |
| GET | `/api/runs/{run_id}` | `api_get_run` | `main` | read-only | reads run | Atlas stores | no | later | yes |
| GET | `/api/runs/{run_id}/log` | `api_get_run_log` | `main` | read-only | reads log | run filesystem | no | later | yes |
| GET | `/api/runs/{run_id}/report` | `api_get_run_report` | `main` | read-only | reads report | run filesystem | no | later | yes |
| GET | `/api/runs/{run_id}/patches` | `api_get_run_patches` | `main` | read-only | reads patches | run filesystem | no | later | yes |
| GET | `/api/runs/{run_id}/patch-dashboard` | `api_get_run_patch_dashboard` | `main` | read-only | reads dashboard | run filesystem | no | later | yes |
| GET | `/api/runs/{run_id}/patches/{patch_id}` | `api_get_run_patch` | `main` | read-only | reads patch | run filesystem | no | later | yes |
| GET | `/api/runs/{run_id}/patches/{patch_id}/chain` | `api_get_run_patch_chain` | `main` | read-only | reads patch chain | run filesystem | no | later | yes |
| GET | `/api/runs/{run_id}/patch_approvals` | `api_get_run_patch_approvals` | `main` | read-only | reads approvals | run stores | no | later | yes |
| POST | `/api/runs/{run_id}/patches/{patch_id}/approve` | `api_approve_patch` | `main` | write | approves patch | run stores/git | no | later | yes |
| POST | `/api/runs/{run_id}/patches/{patch_id}/reject` | `api_reject_patch` | `main` | write | rejects patch | run stores | no | later | yes |
| POST | `/api/runs/{run_id}/patches/{patch_id}/apply` | `api_apply_patch` | `main` | write / heavy | applies patch | git/filesystem | no | later | yes |
| POST | `/api/runs/{run_id}/patches/{patch_id}/reproposal` | `api_generate_reproposal` | `main` | write / heavy | generates reproposal | LLM/Atlas | no | later | yes |
| GET | `/api/runs/{run_id}/verification/{verification_id}` | `api_get_verification_result` | `main` | read-only | reads verification | run stores | no | later | yes |
| GET | `/api/runs/{run_id}/llm-telemetry` | `api_get_llm_telemetry` | `main` | read-only | reads telemetry | telemetry stores | no | later | yes |
| GET | `/api/runs/{run_id}/llm-telemetry/{telemetry_id}` | `api_get_llm_telemetry_one` | `main` | read-only | reads telemetry item | telemetry stores | no | later | yes |
| POST | `/api/runs/{run_id}/patches/{patch_id}/manual-check` | `api_save_manual_check` | `main` | write | saves manual check | run stores | no | later | yes |
| GET | `/api/runs/{run_id}/manual-checks` | `api_get_manual_checks` | `main` | read-only | reads checks | run stores | no | later | yes |
| GET | `/api/runs/{run_id}/manual-checks/{check_id}` | `api_get_manual_check` | `main` | read-only | reads check | run stores | no | later | yes |
| GET | `/api/reviews/{review_id}` | `api_get_review` | `main` | read-only | reads review | review stores | no | later | yes |
| GET | `/api/reviews/{review_id}/markdown` | `api_get_review_markdown` | `main` | read-only | renders review | review stores | no | later | yes |
| GET | `/api/requirements/{requirement_id}` | `api_get_requirement` | `main` | read-only | reads requirement | requirement stores | no | later | yes |
| GET | `/api/requirements/{requirement_id}/markdown` | `api_get_requirement_markdown` | `main` | read-only | renders requirement | requirement stores | no | later | yes |
| POST | `/api/requirements/answer` | `api_answer_requirement` | `main` | write | saves answer | requirement stores | no | later | yes |
| POST | `/api/task/continue` | `api_task_continue` | `main` | write / heavy | continues task | Atlas/LLM runner | no | later | yes |
| POST | `/api/debug/atlas/seed-plan` | `api_debug_atlas_seed_plan` | `main` | write / debug | seeds debug plan | Atlas stores | no | later | yes |
| POST | `/api/debug/atlas/seed-clarification` | `api_debug_atlas_seed_clarification` | `main` | write / debug | seeds debug clarification | Atlas stores | no | later | yes |
| POST | `/agent/start` | `agent_start` | `main` | write / heavy | starts agent | agent manager | no | later | yes |
| POST | `/agent/stop` | `agent_stop` | `main` | write | stops agent | agent manager | no | later | yes |
| POST | `/agent/turn` | `agent_turn` | `main` | write / heavy | advances agent | agent manager/LLM | no | later | yes |
| GET | `/agent/tasks` | `agent_tasks` | `main` | read-only | lists tasks | agent manager | no | later | yes |
| POST | `/agent/tasks/{task_id}/decision` | `agent_task_decision` | `main` | write | records decision | agent manager | no | later | yes |
| POST | `/agent/tasks/{task_id}/run` | `agent_task_run` | `main` | write / heavy | runs task | agent manager | no | later | yes |
| POST | `/agent/tasks/{task_id}/cancel` | `agent_task_cancel` | `main` | write | cancels task | agent manager | no | later | yes |
| POST | `/agent/tasks/{task_id}/revise` | `agent_task_revise` | `main` | write | revises task | agent manager | no | later | yes |
| GET | `/skills` | `list_skills_api` | `main` | read-only | lists skills | skill registry/files | no | later | yes |
| POST | `/skills` | `create_skill_api` | `main` | write | creates skill | skill registry/files | no | later | yes |
| DELETE | `/skills/{name}` | `delete_skill_api` | `main` | write | deletes skill | skill registry/files | no | later | yes |
| POST | `/skills/reload` | `reload_skills` | `main` | write | reloads registry | skill registry | no | later | yes |
| GET | `/git/status` | `git_status_api` | `main` | read-only | probes git | git subprocess/repo | no | later | yes |
| POST | `/git/commit` | `git_commit_api` | `main` | write | commits changes | git subprocess/repo | no | later | yes |
| POST | `/git/checkout` | `git_checkout_api` | `main` | write | checks out branch | git subprocess/repo | no | later | yes |
| POST | `/git/reset` | `git_reset_api` | `main` | write | resets repo | git subprocess/repo | no | later | yes |
| GET | `/git/diff` | `git_diff_api` | `main` | read-only | reads diff | git subprocess/repo | no | later | yes |
| GET | `/git/log` | `git_log_api` | `main` | read-only | reads log | git subprocess/repo | no | later | yes |
| POST | `/mcp` | `mcp_server_endpoint` | `main` | write / integration | handles MCP request | MCP manager/session | no | later | yes |
| GET | `/mcp/info` | `mcp_info` | `main` | read-only | reads MCP info | MCP config | no | later | yes |
| GET | `/repo/config` | `get_repo_config` | `main` | read-only | reads repo config | repo config store | no | later | yes |
| POST | `/repo/config` | `save_repo_config` | `main` | write | saves repo config | repo config store | no | later | yes |
| POST | `/repo/init` | `init_repo` | `main` | write | initializes repo | git/filesystem | no | later | yes |
| POST | `/repo/sync` | `sync_repo` | `main` | write / heavy | syncs repo | git/network/filesystem | no | later | yes |
| GET | `/repo/test-connection` | `test_repo_connection` | `main` | read-only / diagnostic | tests remote connection | git/network | no | later | yes |
| GET | `/repo/status` | `get_repo_status` | `main` | read-only | reads repo status | git/filesystem | no | later | yes |
| GET | `/memory` | `list_memory` | `main` | read-only | lists memory | memory store | no | later | yes |
| POST | `/memory` | `create_memory` | `main` | write | creates memory | memory store | no | later | yes |
| PUT | `/memory/{mid}` | `update_memory` | `main` | write | updates memory | memory store | no | later | yes |
| DELETE | `/memory/{mid}` | `delete_memory_api` | `main` | write | deletes memory | memory store | no | later | yes |
| POST | `/memory/analyze/{job_id}` | `trigger_memory_analysis` | `main` | write / heavy | analyzes memory for job | memory store/LLM/jobs | no | later | yes |
| GET | `/debug/tests` | `debug_tests_home` | `main` | UI / debug | serves debug test UI | debug test runner | no | later | yes |
| POST | `/api/debug/tests/run-all` | `debug_tests_run_all` | `main` | write / heavy / debug | starts tests | test runner/subprocess | no | later | yes |
| GET | `/api/debug/tests/runs/{run_id}` | `debug_tests_run_status` | `main` | read-only / debug | reads test run | test runner state | no | later | yes |
| GET | `/debug/tests/runs/{run_id}` | `debug_tests_run_view` | `main` | UI / debug | serves run view | test runner state | no | later | yes |

## Recommended next PR sequence

1. **PR4.42: Move low-risk system read-only endpoints into `app/api/system_status.py`** — completed
   - Moved endpoints:
     - `GET /health`
     - `GET /system/summary`
     - `GET /system/usage`
   - Production `main.app` uses providers to preserve existing payload shapes.
   - `create_app()` uses no-probe fallbacks.
   - `GET /system/usage/debug` remains in `main.py` because it is diagnostic-oriented.

2. **PR4.43: Move project read-only endpoints into `app/api/projects.py`** — completed
   - Moved endpoints:
     - `GET /projects`
     - `GET /projects/{project}/history`
     - `GET /projects/{project}/files`
   - Production `main.app` installs app-state providers to preserve the existing filesystem/database-backed response shapes.
   - `create_app()` uses lightweight fallbacks and does not scan the filesystem, touch `CA_DATA`, jobs, Nexus, or LLM/runtime state.
   - Project creation/deletion, project download/archive, job, background execution, polling, and streaming routes remained in `main.py` until PR4.44.

3. **PR4.44: Move project/job read-only status endpoints into `app/api/jobs.py`** — completed
   - Moved endpoints:
     - `GET /projects/{project}/jobs`
     - `GET /jobs/{job_id}/poll`
   - Production `main.app` installs app-state providers to preserve the existing job list and poll response shapes.
   - `create_app()` uses lightweight fallbacks and does not touch the filesystem, job registry, LLM, ASR, TTS, or background execution.
   - `POST /jobs/submit` remained in `main.py` at this point as a write/heavy runtime execution endpoint.

4. **PR4.45: Harden settings router ownership and route-shadowing contracts** — completed
   - Confirmed `app/api/settings.py` owns `GET /settings`, `POST /settings`, `GET /settings-defaults`, `GET /settings/defaults`, `GET /settings/{key}`, and `PUT /settings/{key}`.
   - Locked the static defaults routes ahead of `/settings/{key}` so `/settings/defaults` cannot be captured as a dynamic key.
   - Production `main.app` keeps settings provider implementations in `main.py` and registers them on `app.state`; `create_app()` keeps conservative fallback reads and echo-only fallback writes.

5. **PR4.46: Move Nexus read-only status/list endpoints into `app/api/nexus.py`** — completed
   - Moved endpoints:
     - `GET /nexus/summary`
     - `GET /nexus/documents`
     - `GET /nexus/jobs/active`
     - `GET /nexus/web/status`
   - Production `main.app` installs app-state providers to preserve the existing Nexus response shapes.
   - `create_app()` uses lightweight fallbacks and does not touch Nexus DB/filesystem/index, LLM, SearXNG process/network probes, job registries, or background execution.
   - Nexus research, ingest, upload, delete, write, source, news, market, and POST routes remain in the existing Nexus router.

6. **PR4.47: Move Echo read-only status/session endpoints into `app/api/echo.py`** — completed
   - Moved endpoints:
     - `GET /echo/save-status`
     - `GET /echo/sessions`
     - `GET /echo/sessions/{filename:path}`
   - Production `main.app` installs app-state providers to preserve the existing Echo save-status/session-list/session-download response shapes.
   - `create_app()` uses lightweight fallbacks and does not touch EchoVault directories, audio files, ASR/TTS/SBV2 runtime, WebSocket handling, or LLM calls.
   - WebSocket `/echo/stream` remains in `main.py` because it is streaming/runtime execution.
   - `POST /voice/transcribe`, `POST /tts/synthesize`, and `POST /tts/synthesize-batch` remain in `main.py` because they are audio runtime execution endpoints.

7. **PR4.48: lightweight runtime write controls** — completed
   - Moved endpoints: `POST /search/enable`, `POST /search/disable`, `POST /search/num`, `POST /streaming/enable`, `POST /streaming/disable`, and `POST /llm/ctx`.
   - Production `main.app` installs runtime write providers to preserve existing response shapes and state-saving behavior.
   - `create_app()` uses lightweight fallbacks and does not touch llama-server, the model manager, LLM HTTP endpoints, SearXNG process management, ASR/TTS, filesystem scans, job execution, or WebSocket execution.
   - Jobs submit/background execution, Nexus write/research/ingest, Echo WebSocket execution, TTS, ASR, model loading/switching, model scans/benchmarks/downloads, and model process lifecycle controls remained in `main.py` or their existing routers at this point for dedicated plans and contract tests.

8. **PR4.49: Extract job execution runtime into `app/services/jobs.py`** — completed
   - Added `app/services/jobs.py` with `submit_job_service`, `run_job_background_service`, `append_job_event`, `finalize_job`, and `fail_job`; the service module has no HTTP decorators and does not import `main.py`.
   - `POST /jobs/submit` route owner remained `main.py` for PR4.49; the route handler only delegated to `submit_job_service` and returned the existing queued response shape.
   - `main.py` kept a backward-compatible `run_job_background` wrapper so existing background task registration and tests kept using the same entry point while the runtime body lives in `run_job_background_service`.
   - `GET /jobs/{job_id}/poll` and `GET /projects/{project}/jobs` remained owned by `app.api.jobs`; this PR did not change read-only job routes.
   - PR4.50 could move `POST /jobs/submit` to `app/api/jobs.py` because job submit/background execution was behind an explicit service boundary.

9. **PR4.50: Move job submit route into jobs router** — completed
   - `POST /jobs/submit` is now owned by `app.api.jobs` through `submit_job_api`.
   - `create_app()` exposes a conservative unavailable fallback for submit requests and does not touch background tasks, LLM/runtime state, filesystem writes, or the job registry.
   - Production `main.app` registers `app.state.job_submit_provider = job_submit_payload`; main.py keeps only the `job_submit_provider` dependency assembly that calls `submit_job_service`.
   - The job execution runtime remains in `app/services/jobs.py`, with the background body still delegated to `run_job_background_service`.
   - Nexus execution, Echo/ASR/TTS runtime routes, model auto-load/switch, llama-server lifecycle, and UI behavior remain out of scope.

10. **PR4.51: Extract Nexus execution runtime into `app/services/nexus_execution.py`** — completed
   - Added `app/services/nexus_execution.py` with route-neutral service functions for Nexus research, deep/recursive research delegation, document ingest/upload delegation, indexing/report boundaries, web search/SearXNG execution response shaping, source search, evidence addition, follow-up, and ask execution.
   - Nexus execution runtime extracted without importing `main.py`, without `APIRouter`, and without route decorators in the service module.
   - Nexus route owner remained unchanged in PR4.51: POST/write/research/ingest routes stayed in `app.nexus.router` for this PR.
   - app/api/nexus.py owned only read-only/status/list Nexus endpoints in PR4.51: `GET /nexus/summary`, `GET /nexus/documents`, `GET /nexus/jobs/active`, and `GET /nexus/web/status`.
   - Nexus write/research/ingest route movement was deferred to PR4.52, after this service boundary.
   - Jobs submit stays owned by `app/api/jobs.py`; Echo / ASR / TTS execution routes and model auto-load / switch stay in `main.py`.

11. **PR4.52: Move Nexus write/research/ingest routes into `app/api/nexus.py`** — completed
   - `POST /nexus/upload`, `/nexus/search`, `/nexus/web/search`, `/nexus/web/research`, `/nexus/research/run`, `/nexus/sources/search`, `/nexus/evidence/add-from-chunks`, `/nexus/research/jobs/{job_id}/followup`, `/nexus/web/collect`, `/nexus/ask`, and `/nexus/report/build` are now owned by `app.api.nexus`.
   - Production `main.app` registers Nexus write/research providers on `app.state`; main.py keeps only Nexus provider dependency assembly.
   - The Nexus execution runtime remains in `app/services/nexus_execution.py`.
   - `create_app()` exposes conservative unavailable fallbacks and does not touch LLM, SearXNG, filesystem heavy scans, indexing, persistence, or job execution for moved write/research routes.
   - `app.nexus.router` intentionally still owns remaining non-moved Nexus routes such as document delete/download/detail, research readbacks, source file/chunk readbacks, news/market MVP, and watchlists.

12. **PR4.53: Clean up Nexus routing residue and lock route ownership after v2.8 baseline** — completed
   - `KasaneCore_v2.8` (`e94c20dfe0d23e233f4dbc817af994408e739b80`) is the normal recovery baseline for this cleanup pass.
   - PR4.52後、Nexus / Lumen / ASR / TTS / LLM are recorded as healthy; this PR intentionally does not touch LLM, ASR, TTS, Runpod CUDA, UI, jobs execution, model auto-load, or model switch behavior.
   - Moved Nexus HTTP route ownership is locked to `app/api/nexus.py`: read-only Nexus status/list routes plus POST write/research/ingest/provider-dispatch routes live there.
   - Nexus execution body ownership is locked to `app/services/nexus_execution.py`; the service module must not import `main.py` or define `APIRouter` / route decorators.
   - `app/nexus/router.py` remains only for provider payload helper / legacy wrapper dependency assembly and non-moved Nexus routes: document health/detail/delete/download, job/research/source readbacks, news/market MVP, watchlists, export, and report subrouters. Moved Nexus POST route decorators must not return there.
   - Route inventory was regenerated with `python scripts/export_route_inventory.py`; duplicate path/method entries are forbidden.


13. **PR4.54: Inventory Echo/ASR/TTS runtime boundaries and prepare safe service seams** — in progress
   - Echo / ASR / TTS / SBV2 endpoint and runtime boundaries are inventoried in `docs/echo_audio_runtime_inventory.md`.
   - `app/services/audio_runtime.py` adds only route-neutral dataclasses, static endpoint ownership metadata, and pure payload helpers; it does not import `main.py`, define `APIRouter`, import audio runtime stacks, run CUDA probes, or load ASR/TTS/SBV2 models.
   - Echo read-only remains already extracted to `app/api/echo.py`; Echo stream/write remains `main.py` high-risk.
   - ASR runtime remains `main.py` high-risk for POST `/voice/transcribe` and POST `/voice/load`; GET `/voice/status` and GET `/asr/config` moved to `app/api/audio.py` in PR4.56 with provider-backed production payloads and safe fallbacks.
   - TTS/SBV2 runtime route ownership remains `main.py` high-risk for POST `/tts/synthesize`, POST `/tts/synthesize-batch`, SBV2 prepare, and upload routes; PR4.57 delegates the POST `/tts/synthesize` non-streaming body, PR4.58 delegates the POST `/tts/synthesize-batch` batch body, and PR4.59 delegates the POST `/api/tts/style-bert-vits2/prepare` body to `app/services/audio_runtime.py`, while SBV2 models and preview-normalization moved to `app/api/audio.py` in PR4.56.
   - Next planned sequence:
     - PR4.55: Extract ASR/TTS service functions without moving routes.
     - PR4.56: Move low-risk audio status/config routes to `app/api/audio.py` (complete).
     - PR4.57: Extract TTS/SBV2 non-streaming service body without moving WebSocket/Echo stream (complete).
     - PR4.58: Extract TTS/SBV2 synthesize-batch service body without moving routes (complete).
     - PR4.59: Extract SBV2 prepare service body without moving routes (complete).
     - PR4.60+: ASR load/transcribe inventory or extraction before Echo WebSocket last.

## PR4.55 audio runtime helper extraction state

PR4.55 is complete when the audio runtime helper seam is `app/services/audio_runtime.py` and route ownership remains unchanged.  The seam contains payload/helper/diagnostic shaping only: voice status response construction, ASR config response construction, audio runtime debug response construction, ASR/TTS degraded status classification, ASR/TTS device and `compute_type` display formatting, SBV2 model/runtime status display formatting, normalized error/degraded reasons, and endpoint risk / ownership metadata.

Current ownership after PR4.59:

- PR4.56 moved GET `/voice/status`, GET `/asr/config`, GET `/audio/runtime/debug`, GET `/api/tts/style-bert-vits2/models`, and POST `/api/tts/style-bert-vits2/preview-normalization` to `app/api/audio.py`.
- `main.py` remains the owner for POST `/voice/load`, POST `/voice/transcribe`, POST `/tts/synthesize`, POST `/tts/synthesize-batch`, POST `/api/tts/style-bert-vits2/prepare`, WebSocket `/echo/stream`, and SBV2 upload routes.
- Audio router production collection remains provider-backed from `main.py`, and debug payload shaping is delegated to `app/services/audio_runtime.py`.
- PR4.57 extracts the non-streaming POST `/tts/synthesize` body into `run_tts_synthesize_service_body()` with injected production dependencies.
- PR4.58 extracts the POST `/tts/synthesize-batch` body into `run_tts_synthesize_batch_service_body()` with injected production dependencies.
- PR4.60 extracted the POST `/voice/load` service body while keeping route ownership in `main.py`.
- WebSocket `/echo/stream`, transcribe, and Echo write/delete bodies remain in `main.py`; SBV2 prepare route ownership remains `main.py` but its service body is extracted.
- The import-time CUDA probe ban continues: `app/services/audio_runtime.py` must not top-level import `torch`, `ctranslate2`, `faster_whisper`, or Style-Bert-VITS2 runtime modules, and must not call `detect_audio_runtime()` during import.

Next candidates:

1. PR4.61: Inventory and stabilize ASR transcribe seams before extraction.
2. PR4.62: Extract `/voice/transcribe` service body without moving route.
3. PR4.63: Stabilize Echo stream ASR reuse seam.
4. PR4.64+: Echo WebSocket extraction last.


## PR4.56 low-risk audio read/status router move

- Moved GET `/voice/status`, GET `/asr/config`, GET `/audio/runtime/debug`, GET `/api/tts/style-bert-vits2/models`, and POST `/api/tts/style-bert-vits2/preview-normalization` to `app/api/audio.py`.
- Production `main.app` registers providers for those routes so existing response shapes and runtime behavior are preserved.
- `create_app()` fallbacks are side-effect-free: no model load, no CUDA probe, no heavy filesystem scan, and no direct LLM fallback.
- Execution/high-risk audio routes remain `main.py`: POST `/voice/load`, POST `/voice/transcribe`, POST `/tts/synthesize`, POST `/tts/synthesize-batch`, POST `/api/tts/style-bert-vits2/prepare`, and WebSocket `/echo/stream`; TTS/SBV2 service bodies and the POST `/voice/load` service body are extracted, while ASR transcribe and Echo streaming remain high-risk bodies.


## PR4.61 ASR transcribe seam inventory state

- PR4.61時点: POST `/voice/load` は service body 抽出済みとして扱い、route owner は引き続き `main.py`。
- PR4.62時点: POST `/voice/transcribe` は service body 抽出済みで、route owner は引き続き `main.py`。
- PR4.61時点: WebSocket `/echo/stream` は `main.py` に残留し、Echo session write/delete と合わせて今回未変更。
- `docs/asr_transcribe_runtime_inventory.md` が、JSON input、base64 bytes handling、temporary file suffix、faster-whisper call、CUDA fallback、cpu-int8 fallback、degraded reason、response payload shape、error payload shape、debug/status fields、Echo共有点を固定する。
- `app/services/audio_runtime.py` には `VoiceTranscribeServiceDependencies` / `VoiceTranscribeServiceResponse` / `run_voice_transcribe_service_body` を追加済み。

Next sequence after PR4.62:

1. PR4.63: Stabilize Echo stream ASR reuse seam before WebSocket extraction.
2. PR4.64+: Echo WebSocket extraction last.


## PR4.62 ASR transcribe service extraction state

- PR4.62 で POST `/voice/transcribe` の service body を `app/services/audio_runtime.py` に抽出。
- route owner は `main.py` のまま。
- `/voice/load` と `/voice/transcribe` は service body 抽出済み。
- WebSocket `/echo/stream` は `main.py` に残留。
- Echo stream extraction は最後に回す。

## PR4.63 Echo stream ASR reuse seam status

PR4.63 records the Echo stream ASR reuse seam before moving any WebSocket code:

- POST `/voice/load` は service body 抽出済み。
- POST `/voice/transcribe` は service body 抽出済み。
- WebSocket `/echo/stream` は `main.py` に残留。
- Echo stream ASR reuse seam を棚卸し済み。
- Route owner and `echo_stream_ws` websocket loop remain in `main.py`; websocket message shape, Echo session writes, CUDA fallback, and debug entry format are frozen.

Next sequence:

- PR4.64: Extract Echo stream ASR helper body without moving WebSocket.
- PR4.65: Extract Echo session write/save helper body.
- PR4.66+: WebSocket route extraction last.

## PR4.64 Echo stream ASR helper-body extraction

- PR4.64 extracts the Echo stream ASR helper body around `_echo_voice_transcribe(...)` into `app/services/audio_runtime.py` as route-neutral service code with `EchoStreamAsrServiceDependencies`, `EchoStreamAsrServiceResponse`, and `run_echo_stream_asr_service_body(...)`.
- WebSocket `/echo/stream` route owner remains `main.py`; the `echo_stream_ws` main loop remains in `main.py` and is not moved.
- `_echo_voice_transcribe(...)` remains in `main.py` as a thin wrapper that assembles production dependencies and calls the service helper.
- WebSocket message shape must not change: status, ack, sentence, translation, error, and ui_log payload keys remain owned by the existing `main.py` WebSocket flow.
- Echo session write/save/delete behavior is not moved in PR4.64 and remains high risk for a later PR.
- Remaining high-risk areas after PR4.64: Echo WebSocket loop, Echo session write/save, and Echo TTS chain.

## PR4.65 Root directory cleanup inventory pause

- PR4.64 で Echo stream ASR helper body は `app/services/audio_runtime.py` に抽出済み。
- PR4.65 は root directory cleanup inventory のみを扱い、実際の root直下ファイル移動は行わない。
- WebSocket `/echo/stream` route移動はまだ保留し、route owner は `main.py` のまま固定する。
- Audio/Echo runtime の route ownership は変更しない。
- root cleanup 実移動後に Echo session write/save 抽出へ戻る。

## PR4.66 Root cleanup low-risk move

- PR4.66 は root cleanup の最初の実移動として、低リスク utility のみを移動する。
- `agent_runtime.py` は `tools/agent_runtime.py` へ移動した。
- `DLllama.bat` は `tools/DLllama.bat` へ移動した。
- runtime route ownership には変更なし。
- Audio/Echo/ASR/TTS/SBV2 実行コードには変更なし。
- WebSocket `/echo/stream` は未移動で、route owner は `main.py` のまま。
- Echo session write/save/delete と Echo TTS chain の高リスク領域は引き続き後続PRへ保留する。

## PR4.67 Echo session write/save helper-body extraction

- PR4.67 extracts the Echo session write/save helper body into `app/services/audio_runtime.py` without moving WebSocket `/echo/stream`.
- WebSocket `/echo/stream` route owner remains `main.py`; `echo_stream_ws` main loop remains in `main.py`.
- Echo ASR helper and session write/save helper bodies are extracted. The route still owns WebSocket accept/receive/send/close, ASR result sends, and the Echo TTS chain.
- WebSocket message shape must not change.
- Echo session save destination and filename format must not change, and `/echo/save-status` plus `/echo/sessions` read ownership remains unchanged in `app/api/echo.py`.
- Remaining high-risk: Echo TTS chain, Echo WebSocket loop, and WebSocket route extraction.

## PR4.68 Lumen / Jobs boundary update

- `POST /jobs/submit` remains owned by `app.api.jobs`, but its production provider now creates only Lumen chat jobs.
- Legacy task payloads are rejected before job creation so stale UI payloads cannot start background work.
- Main still assembles runtime dependencies for Lumen chat execution; Atlas/Agent and Nexus keep autonomous execution and research ownership respectively.

## PR4.68a Lumen chat-only core note

- PR4.68a adds Lumen's chat-only core and `app/lumen/` domain skeleton for future lightweight tools.
- Legacy task mode is deleted/rejected for the Lumen `/jobs/submit` path; `task`, `legacy_task`, and `agent_task` payloads must fail before job creation.
- `/jobs/submit` is currently a Lumen chat-compatible endpoint owned by `app/api/jobs.py`.
- Moving the Lumen submit route to `app/api/lumen.py` is planned for PR4.68d, not this PR.
- UI splitting is planned for PR4.68e, not this PR.
