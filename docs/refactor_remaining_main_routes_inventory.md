# PR4.44: Project/job read-only status endpoints moved into `app/api/jobs.py`

## Scope and guardrails

This document records the PR4.44 extraction of job read-only status endpoints into `app/api/jobs.py`, building on PR4.42 system status and PR4.43 project read-only router work. The move keeps production responses provider-backed while preserving lightweight app-factory fallbacks.

Hard guardrails retained for this PR:

- Do not move diagnostic/heavy system endpoints such as `/system/usage/debug`.
- Do not change non-target `main.py` behavior.
- Do not change LLM / ASR / TTS / SBV2 / Runpod llama search behavior.
- Do not change `app/api/runtime_controls.py` or `app/api/model_settings.py`.
- Do not move `POST /jobs/submit`, background job execution, Nexus, Echo, ASR, TTS, or UI behavior.
- Do not change UI assets, Echo WebSocket handling, `/model/switch`, `/model/auto-load`, `/debug/llama`, or `benchmark_mem.py`.

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
| POST | `/llm/ctx` | `set_ctx` | `main` | write | mutates runtime context setting | `_current_n_ctx`, settings | no | not next | yes |
| GET | `/llm/props` | `get_runtime_llm_props_api` | `app.api.runtime_controls` | read-only / diagnostic | may inspect runtime | runtime provider | yes | already moved | yes |
| GET | `/search/status` | `get_search_status_api` | `app.api.runtime_controls` | read-only | none | runtime provider | yes | already moved | yes |
| GET | `/streaming/status` | `get_streaming_status_api` | `app.api.runtime_controls` | read-only | none | runtime provider | yes | already moved | yes |
| GET | `/runtime/cuda-debug` | `get_runtime_cuda_debug_api` | `app.api.runtime_controls` | read-only / diagnostic | runtime diagnostics | runtime provider | yes | already moved | yes |
| GET | `/audio/runtime/debug` | `get_audio_runtime_debug_api` | `app.api.runtime_controls` | read-only / diagnostic | audio runtime diagnostics | audio providers/registries | yes | already moved | yes |
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

Settings endpoints are already router-owned. Treat them as out of scope for the next split because write/update paths require persistence-provider care.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/settings` | `get_settings_api` | `app.api.settings` | read-only | none | settings provider | yes | already moved | yes in PR4.41 |
| POST | `/settings` | `save_settings_api` | `app.api.settings` | write | persists settings when provider exists | settings provider/database | fallback echo only | not next | yes |
| GET | `/settings-defaults` | `get_settings_defaults_api` | `app.api.settings` | read-only | none | settings provider | yes | already moved | yes |
| GET | `/settings/defaults` | `get_settings_defaults_legacy_api` | `app.api.settings` | read-only | none | settings provider | yes | already moved | yes |
| GET | `/settings/{key}` | `get_setting_api` | `app.api.settings` | read-only | none | settings provider | yes | already moved | yes |
| PUT | `/settings/{key}` | `set_setting_api` | `app.api.settings` | write | persists one setting when provider exists | settings provider/database | fallback echo only | not next | yes |

## D. Project / file / job candidates

PR4.43 moved the low-risk project read-only list/history/file endpoints to `app.api.projects`. PR4.44 moved the job read-only status endpoints `GET /projects/{project}/jobs` and `GET /jobs/{job_id}/poll` to `app.api.jobs` with provider-backed production payloads and lightweight `create_app()` fallbacks. `POST /jobs/submit` remains in `main.py` because it is a write/heavy runtime execution endpoint that starts background job work.

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
| POST | `/jobs/submit` | `submit_job` | `main` | write / heavy / runtime execution | starts background job execution | job manager, LLM/runtime globals | no | keep in `main.py` after PR4.44 | yes |
| GET | `/jobs/{job_id}` | `get_job` | `main` | read-only | reads job state | job registry/store | no | later, separate from PR4.44 poll/list move | yes |
| GET | `/jobs/{job_id}/poll` | `get_job_poll_api` | `app.api.jobs` | read-only / polling | reads job state through provider | provider-backed job registry/store on `main.app` | yes: empty done poll payload | moved in PR4.44 | no |
| GET | `/jobs/{job_id}/stream` | `stream_job` | `main` | streaming | streams job events/logs | job registry/streaming response | no | PR4.44+ after non-streaming jobs | yes |
| POST | `/jobs/{job_id}/respond` | `respond_to_job` | `main` | write | sends response to active job | job manager/queues | no | PR4.44+ | yes |
| GET | `/jobs/{job_id}/logs` | `get_job_logs_api` | `main` | read-only | reads logs | job log filesystem | no | PR4.44+ | yes |
| POST | `/jobs/{job_id}/analyze_skills` | `analyze_job_for_skills` | `main` | write / heavy | launches skill analysis | job manager/LLM/skills | no | PR4.44+ | yes |

## E. Nexus candidates

There are no direct `@app.get('/nexus/...')` or `@app.post('/nexus/...')` decorators remaining in `main.py`; `main.py` mounts the existing Nexus router. Because Nexus includes read-only pages, write operations, exports, and heavy research jobs, do not split it further before project/system work is complete.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mixed | `/nexus/*` | Nexus router handlers | `app.nexus.router` / subrouters | read-only / write / heavy | research state, report/export files | Nexus stores/services | no | PR4.44+ or later only after separate Nexus plan | yes |

## F. Echo / audio candidates

Echo, voice, ASR, and TTS routes are high-risk because they touch streaming, WebSocket state, audio runtimes, uploaded files, model loading, and synthesis workers.

| Method | Path | Handler | Current owner | Kind | Side effect | Globals/managers/registries | create_app fallback | Next move? | Move ban |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/voice/status` | `voice_status_api` | `main` | read-only | inspects ASR state | voice/ASR globals | no | later | yes |
| POST | `/voice/load` | `voice_load_api` | `main` | write / heavy | loads ASR model | ASR runtime manager | no | later | yes |
| POST | `/voice/unload` | `voice_unload_api` | `main` | write / heavy | unloads ASR model | ASR runtime manager | no | later | yes |
| POST | `/voice/transcribe` | `voice_transcribe_api` | `main` | write / heavy | transcribes audio | ASR runtime/files | no | later | yes |
| GET | `/asr/config` | `asr_config_api` | `main` | read-only | reads ASR config | ASR settings/runtime | no | later | yes |
| GET | `/asr/status` | `asr_status_api` | `main` | read-only | reads ASR status | ASR runtime | no | later | yes |
| POST | `/asr/load` | `asr_load_api` | `main` | write / heavy | loads ASR engine | ASR runtime | no | later | yes |
| POST | `/asr/unload` | `asr_unload_api` | `main` | write / heavy | unloads ASR engine | ASR runtime | no | later | yes |
| GET | `/echo/save-status` | `echo_save_status` | `main` | read-only | reads save state | Echo globals/files | no | later | yes |
| GET | `/echo/runtime-status` | `echo_runtime_status` | `main` | read-only | reads runtime state | Echo/audio runtime | no | later | yes |
| WEBSOCKET | `/echo/stream` | `echo_stream_ws` | `main` | websocket / streaming | bidirectional audio session | Echo session/runtime managers | no | not until dedicated WebSocket PR | yes |
| GET | `/debug/echo` | `debug_echo` | `main` | read-only / diagnostic | reads diagnostics | Echo runtime/files | no | later | yes |
| GET | `/debu/echo` | `debug_echo_typo_redirect` | `main` | read-only | compatibility redirect/payload | Echo debug path | no | later | yes |
| POST | `/echo/generate-minutes` | `echo_generate_minutes` | `main` | write / heavy | generates minutes | Echo, LLM, files | no | later | yes |
| POST | `/echo/import-audio-transcript` | `echo_import_audio_transcript` | `main` | write / heavy | imports transcript/audio metadata | Echo files/stores | no | later | yes |
| GET | `/echo/sessions` | `echo_list_sessions` | `main` | read-only | lists sessions | Echo session filesystem | no | later | yes |
| GET | `/echo/sessions/{filename:path}` | `echo_download_session` | `main` | read-only / file response | serves session file | Echo session filesystem | no | later | yes |
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
| POST | `/api/tts/style-bert-vits2/prepare` | `api_style_bert_vits2_prepare` | `main` | write / heavy | prepares SBV2 runtime | SBV2 runtime/files | no | later | yes |
| GET | `/api/tts/style-bert-vits2/models` | `api_style_bert_vits2_models` | `main` | read-only | lists SBV2 models | SBV2 filesystem | no | later | yes |
| POST | `/api/tts/style-bert-vits2/preview-normalization` | `api_style_bert_vits2_preview_normalization` | `main` | write / heavy | normalizes preview input | SBV2/text processing | no | later | yes |
| POST | `/api/tts/style-bert-vits2/models/upload` | `api_style_bert_vits2_models_upload` | `main` | write / heavy | uploads model files | SBV2 filesystem | no | later | yes |
| POST | `/tts/ref-audio/upload` | `tts_ref_audio_upload` | `main` | write | uploads reference audio | TTS ref-audio filesystem | no | later | yes |
| GET | `/tts/ref-audio/list` | `tts_ref_audio_list` | `main` | read-only | lists reference audio | TTS ref-audio filesystem | no | later | yes |
| DELETE | `/tts/ref-audio/{filename}` | `tts_ref_audio_delete` | `main` | write | deletes reference audio | TTS ref-audio filesystem | no | later | yes |
| POST | `/tts/synthesize` | `tts_synthesize_api` | `main` | write / heavy | synthesizes audio | TTS engine registry/runtime | no | later | yes |
| POST | `/tts/synthesize-batch` | `tts_synthesize_batch_api` | `main` | write / heavy | batch synthesis | TTS engine registry/runtime | no | later | yes |

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
   - `POST /jobs/submit` remains in `main.py` as a write/heavy runtime execution endpoint.

4. **PR4.45以降**
   - Jobs submit/background execution, Nexus, Echo, TTS, ASR, model loading/switching, model scans/benchmarks/downloads, and WebSocket/streaming endpoints are heavy and should wait for dedicated plans and contract tests.
