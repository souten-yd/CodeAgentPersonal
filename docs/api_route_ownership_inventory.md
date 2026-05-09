# API Route Ownership Inventory

この表は、現在の endpoint 所有者・risk・fallback/provider の有無を固定して、手書き docs と実装のズレを見つけやすくするための inventory です。自動一覧は `python scripts/export_route_inventory.py` で `docs/generated/route_inventory.md` / `.json` に出力できます。

| endpoint | method | owner module | service module | risk level | status | create_app fallback 有無 | production provider 有無 |
|---|---:|---|---|---|---|---|---|
| `/health` | GET | `app/api/health.py`, `app/api/system_status.py` | n/a | low | health/read-only | yes | no |
| `/system/summary` | GET | `app/api/system_status.py` | `app/services/system_usage.py` where applicable | low | read-only | yes | yes |
| `/system/usage` | GET | `app/api/system_status.py` | `app/services/system_usage.py` where applicable | low | read-only | yes | yes |
| `/system/readiness` | GET | `app/api/system.py` | n/a | low | read-only | yes | no |
| `/system/env` | GET | `app/api/system.py` | n/a | low | read-only | yes | no |
| `/nexus/summary` | GET | `app/api/nexus.py` | provider-backed | low | read-only | yes | yes |
| `/nexus/dashboard/summary` | GET | `app/api/nexus.py` | provider-backed | low | read-only alias | yes | yes |
| `/nexus/documents` | GET | `app/api/nexus.py` | provider-backed | low | read-only | yes | yes |
| `/nexus/library/documents` | GET | `app/api/nexus.py` | provider-backed | low | read-only alias | yes | yes |
| `/nexus/jobs/active` | GET | `app/api/nexus.py` | provider-backed | low | read-only | yes | yes |
| `/nexus/web/status` | GET | `app/api/nexus.py` | provider-backed | low | read-only | yes | yes |
| `/echo/save-status` | GET | `app/api/echo.py` | provider-backed | low | read-only | yes | yes |
| `/echo/sessions` | GET | `app/api/echo.py` | provider-backed | low | read-only | yes | yes |
| `/echo/sessions/{filename:path}` | GET | `app/api/echo.py` | provider-backed | medium | read-only file access | yes | yes |
| `/jobs/submit` | POST | `app/api/jobs.py` | `app/services/jobs.py` and production provider | high | execution route | yes | yes |
| job execution body | n/a | `app/services/jobs.py` | `app/services/jobs.py` | high | service | n/a | n/a |
| `/projects/{project}/jobs` | GET | `app/api/jobs.py` | provider-backed | medium | read-only/history | yes | yes |
| `/jobs/{job_id}/poll` | GET | `app/api/jobs.py` | provider-backed | medium | read-only/status | yes | yes |
| `/llm/ctx` | GET/POST | `app/api/runtime_controls.py` | provider-backed | medium | runtime control/status | yes | yes |
| `/llm/props` | GET | `app/api/runtime_controls.py` | provider-backed | low | read-only | yes | yes |
| `/runtime/cuda-debug` | GET | `app/api/runtime_controls.py` | provider-backed | medium | diagnostic read | yes | yes |
| `/audio/runtime/debug` | GET | `app/api/runtime_controls.py` | provider-backed | medium | diagnostic read | yes | yes |
| `/debug/model-startup` | GET | `app/api/runtime_controls.py` | provider-backed | medium | diagnostic read | yes | yes |
| `/search/status` | GET | `app/api/runtime_controls.py` | provider-backed | low | read-only | yes | yes |
| `/search/enable` | POST | `app/api/runtime_controls.py` | provider-backed | medium | runtime control | yes | yes |
| `/search/disable` | POST | `app/api/runtime_controls.py` | provider-backed | medium | runtime control | yes | yes |
| `/search/num` | POST | `app/api/runtime_controls.py` | provider-backed | medium | runtime control | yes | yes |
| `/streaming/status` | GET | `app/api/runtime_controls.py` | provider-backed | low | read-only | yes | yes |
| `/streaming/enable` | POST | `app/api/runtime_controls.py` | provider-backed | medium | runtime control | yes | yes |
| `/streaming/disable` | POST | `app/api/runtime_controls.py` | provider-backed | medium | runtime control | yes | yes |
| `/models/db` | GET | `app/api/model_settings.py` | provider-backed | low | read-only | yes | yes |
| `/models/db/status` | GET | `app/api/model_settings.py` | provider-backed | low | read-only | yes | yes |
| `/model/status` | GET | `app/api/model_settings.py` | provider-backed | low | read-only | yes | yes |
| `/models/roles` | GET | `app/api/model_settings.py` | provider-backed | low | read-only | yes | yes |
| `/models/orchestration` | GET | `app/api/model_settings.py` | provider-backed | low | read-only | yes | yes |
| `/model/auto-load` | POST | `main.py` | ModelManager runtime | high | high-risk runtime | no | n/a |
| `/model/switch` | POST | `main.py` | ModelManager runtime | high | high-risk runtime | no | n/a |
| `/voice/status` | GET | `main.py` | ASR runtime state | medium | audio status; must not CUDA probe | no | n/a |
| `/voice/transcribe` | POST | `main.py` | ASR runtime | high | audio runtime | no | n/a |
| `/voice/load` | POST | `main.py` | ASR runtime | high | audio runtime | no | n/a |
| `/voice/unload` | POST | `main.py` | ASR runtime | high | audio runtime | no | n/a |
| `/tts/synthesize` | POST | `main.py` | TTS/SBV2 runtime | high | audio runtime | no | n/a |
| `/tts/load` | POST | `main.py` | TTS/SBV2 runtime | high | audio runtime | no | n/a |
| `/tts/unload` | POST | `main.py` | TTS/SBV2 runtime | high | audio runtime | no | n/a |
| `/echo/stream` | WebSocket | `main.py` | Echo/ASR/TTS runtime | high | high-risk runtime | no | n/a |
| `/chat` | POST | `main.py` | LLM runtime | high | LLM execution | no | n/a |
| `/stream` | POST | `main.py` | LLM runtime | high | LLM execution | no | n/a |
| `/task` | POST | `main.py` | agent/job runtime | high | execution | no | n/a |
| `/task/stream` | POST | `main.py` | agent/job runtime | high | execution | no | n/a |
| `/api/atlas/*` | GET/POST | `main.py` | Atlas planner/workflow | medium/high | partially split | no | n/a |
| `/agent/*` | GET/POST | `main.py` | Agent runtime | high | execution | no | n/a |

## Notes

- `create_app fallback 有無 = yes` means the app-factory shell can return a conservative payload without touching CUDA, model load, filesystem-heavy scans, ASR/TTS, or live LLM runtime.
- `production provider 有無 = yes` means `main.app` wires a provider that preserves production behavior.
- High-risk runtime routes must not be moved casually in this recovery PR.
