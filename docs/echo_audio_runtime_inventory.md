# PR4.54 Echo / ASR / TTS / SBV2 runtime boundary inventory

PR4.54 is a preparation-only PR after the healthy `KasaneCore_v2.8` baseline.  `KasaneCore_v2.8 == main at e94c20dfe0d23e233f4dbc817af994408e739b80` remains the recovery point where LLM / ASR / TTS / Nexus / Lumen were confirmed healthy, including ASR OK and TTS/SBV2 OK.  This inventory does **not** move routes, change runtime behavior, start model loads, or run CUDA probes at import time.

## Guardrails

- Keep every Echo / ASR / TTS / SBV2 execution route owner unchanged in `main.py` for this PR.
- Do not call `detect_audio_runtime()` at import time.
- Do not import `torch`, `ctranslate2`, `faster_whisper`, or Style-Bert-VITS2 runtime modules from `app/services/audio_runtime.py` at module import time.
- Do not change WebSocket `/echo/stream`, POST `/voice/transcribe`, POST `/tts/synthesize`, POST `/tts/synthesize-batch`, SBV2 normalization, dictionary cache, katakana fallback, LLM fallback, model auto-load, or Runpod CUDA / llama NGL probing.
- `create_app()` fallbacks must remain safe: no CUDA probe, no ASR/TTS model load, no SBV2 runtime prepare, no filesystem-heavy scan, and no LLM fallback generation.


## PR4.55 helper extraction update

PR4.55 extracted only safe ASR/TTS/SBV2 payload shaping and diagnostic shaping into `app/services/audio_runtime.py`. PR4.56 moves low-risk read/status/config ownership for GET `/voice/status`, GET `/asr/config`, GET `/audio/runtime/debug`, GET `/api/tts/style-bert-vits2/models`, and POST `/api/tts/style-bert-vits2/preview-normalization` to `app/api/audio.py`; production payload providers remain registered from `main.py`. PR4.57 extracts the non-streaming POST `/tts/synthesize` service body into `app/services/audio_runtime.py` behind injected production dependencies while keeping the route owner in `main.py`. POST `/voice/transcribe`, POST `/voice/load`, POST `/tts/synthesize`, POST `/tts/synthesize-batch`, POST `/api/tts/style-bert-vits2/prepare`, and WebSocket `/echo/stream` remain owned by `main.py`.

What moved in PR4.55:

- GET `/voice/status` response dict construction now delegates to `build_voice_status_payload(...)`.
- GET `/asr/config` response dict construction now delegates to `build_asr_config_payload(...)`.
- GET `/audio/runtime/debug` provider keeps runtime collection/probes in `main.py`, while final diagnostic dict construction delegates to `build_audio_runtime_debug_payload(...)`.
- TTS/SBV2 status display helpers, degraded classification, device / `compute_type` summary, SBV2 runtime summary, and normalized error/reason formatting now live in `app/services/audio_runtime.py`.

What did **not** move:

- Execution route ownership is still in `main.py`: POST `/voice/transcribe`, POST `/voice/load`, POST `/tts/synthesize`, POST `/tts/synthesize-batch`, and WebSocket `/echo/stream`. PR4.57 moved only the non-streaming `/tts/synthesize` body into an injected service helper; batch synthesis and Echo streaming bodies remain in `main.py`.
- SBV2 normalization / kana fallback / dictionary cache behavior is unchanged.
- `detect_audio_runtime()` timing is unchanged; import-time CUDA probe remains forbidden.

## Endpoint inventory

| Risk | Endpoint / feature | Current owner module | Related helpers / global state | Runtime load | CUDA probe | Filesystem write | LLM fallback | create_app fallback note | Move classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low-risk read/status | GET `/voice/status` | `app/api/audio.py` | `voice_status()`, ASR runtime globals/status fields | No intentional load | Must not probe; status-only | No | No | Needs safe static/provider fallback before route move | Move candidate in PR4.56 after service seams |
| medium-risk write/runtime-load | POST `/voice/load` | `main.py` | `_apply_asr_runtime_settings()`, `voice_load()`, ASR model manager | Yes, ASR runtime load | May use selected ASR device only during explicit load | No direct user file write | No | Fallback should report unavailable, not load | Keep in `main.py` until helper extraction |
| high-risk execution | POST `/voice/transcribe` | `main.py` | `_apply_asr_runtime_settings()`, `_resolve_asr_profile()`, ASR decode/transcribe helpers, audio temp handling | May load/keep ASR model resident | CUDA/device behavior only during explicit transcription/load | Temporary audio decode/write path may be used | Post-filter path must stay unchanged | Fallback should reject without ASR execution | Do not move before PR4.55 helper contracts |
| low-risk read/status | GET `/asr/config` | `app/api/audio.py` | `_resolve_asr_runtime_config()`, `app/audio/runtime_config.py` configuration shape | No model load | Must not call heavy CUDA probe from fallback/import | No | No | Safe provider/static fallback needed | Move candidate in PR4.56 |
| high-risk execution/websocket | WebSocket `/echo/stream` | `main.py` | `_echo_sessions`, `_echo_debug_append()`, `_echo_save_lock`, `_echo_minutes_lock`, ASR chunk handling, TTS response flow | Can invoke ASR/TTS runtime during live session | Device/runtime behavior during explicit stream execution | Writes EchoVault sessions/debug/minutes | Possible through downstream response generation paths; keep unchanged | No WebSocket fallback until dedicated route plan | Move last in PR4.58+ |
| medium-risk write/filesystem | DELETE `/echo/sessions/{filename:path}` | `main.py` | `ECHOVAULT_DIR`, Echo session path sanitizer, session providers | No | No | Deletes EchoVault files | No | Needs provider fallback and path-safety contract | Move only after write seam is explicit |
| medium-risk write/runtime-load | POST `/api/tts/style-bert-vits2/prepare` | `main.py` | `_style_bert_vits2_init_lock`, `_tts_engine_registry`, `_STYLE_BERT_VITS2_*`, SBV2 prepare helpers | Yes, SBV2/TTS runtime prepare | Device choice may touch CUDA during explicit prepare | May initialize/download/prepare local runtime artifacts | No direct preview fallback | Fallback must not initialize runtime | Keep in `main.py` until SBV2 seam is explicit |
| low-risk read/status | GET `/api/tts/style-bert-vits2/models` | `app/api/audio.py` | `_style_bert_vits2_list_models()`, `_style_bert_vits2_describe_model()` | No | No | No | No | Fallback can be empty/static if it avoids heavy scans | Candidate after filesystem rules are fixed |
| low/medium-risk read-preview with LLM fallback caution | POST `/api/tts/style-bert-vits2/preview-normalization` | `app/api/audio.py` | `_tts_engine_registry`, `StyleBertVITS2Runtime.build_normalization_preview()`, normalization, katakana fallback, dictionary cache | No model load intended, but runtime object required | No import-time probe; runtime may already know device | May read/write dictionary/cache depending existing runtime behavior | **Yes/caution** if normalization path asks LLM fallback | Fallback must not invoke LLM or SBV2 runtime | Move only after LLM fallback is contract-tested |
| medium-risk write/filesystem | POST `/api/tts/style-bert-vits2/models/upload` | `main.py` | `import_model_zip()`, `_STYLE_BERT_VITS2_MODELS_DIR`, model list helpers | No TTS synthesis, but changes model inventory | No | Uploads/imports SBV2 model zip | No | Fallback should reject unavailable without writing | Not part of first low-risk move |
| high-risk execution | POST `/tts/synthesize` | `main.py` | `run_tts_synthesize_service_body()`, injected `_tts_engine_registry`, `StyleBertVITS2Runtime`, `_write_tts_debug_entry()`, normalization pipeline | Can prepare/load/use TTS/SBV2 runtime during explicit request | Device/runtime behavior only during explicit synthesis | Writes debug/ref/temp/output artifacts through production dependencies | Possible through SBV2 text normalization fallback path; keep unchanged | Fallback should reject without synthesis | PR4.57 service body extracted; route owner still frozen in `main.py` |
| high-risk execution | POST `/tts/synthesize-batch` | `main.py` | `_run_tts_synthesize_batch()`, job progress helpers, zip/wav streaming, TTS synthesize internals | Uses TTS/SBV2 runtime for every item | Device/runtime behavior during explicit batch synthesis | Writes job/progress/temp zip/wav artifacts | Same normalization fallback caution as single synthesis | Fallback should reject without synthesis | Move only after single synthesize seam is stable |

## Runtime boundary notes

### Runtime load locations

- ASR runtime load is explicit in POST `/voice/load` and can also be reached by high-risk execution flows such as POST `/voice/transcribe` and WebSocket `/echo/stream` if the model must be available for transcription.
- TTS/SBV2 runtime load or prepare is explicit in POST `/api/tts/style-bert-vits2/prepare` and can be used by POST `/tts/synthesize`, POST `/tts/synthesize-batch`, and Echo streaming response paths.
- `app/services/audio_runtime.py` only contains route-neutral dataclasses, constants, and pure helpers; it does not import `main.py` or runtime-heavy audio modules.

### CUDA probe locations

- `app/audio/runtime_config.py` owns `detect_audio_runtime()` and related CUDA/device detection.  It must only be called from explicit diagnostics/runtime paths, not at `main.py` import time and not from the new audio service at import time.
- `/voice/status` and safe `create_app()` fallbacks are status/config boundaries and must not perform CUDA probes.

### Filesystem write locations

- Echo session writes, debug logs, generated minutes, and DELETE `/echo/sessions/{filename:path}` operate under EchoVault/session paths owned by `main.py` today.
- TTS debug entries, temporary audio, batch zip/wav outputs, reference audio, and SBV2 model uploads are write-capable runtime paths that must remain frozen until write seams are explicit.
- SBV2 dictionary cache and normalization support files are part of the runtime behavior and must not be changed in PR4.54.

### LLM fallback locations

- SBV2 normalization / katakana fallback / dictionary cache behavior can involve an LLM fallback depending on runtime configuration and input.  Preview normalization and synthesis routes must keep this behavior unchanged until a later contract explicitly fixes the fallback boundary.
- `create_app()` fallback for preview normalization must not call the LLM fallback; it should be unavailable/static until safe providers are defined.

## create_app() fallback summary

`create_app() fallback` behavior for audio runtime routes must be conservative: return static/provider-unavailable responses only, never execute Echo / ASR / TTS / SBV2 runtime work, never call CUDA probes, and never invoke LLM fallback.

## Route move readiness

### Low-risk read/status candidates

- GET `/voice/status`: moved to `app/api/audio.py` in PR4.56; production reports live ASR state through a provider and `create_app()` returns a no-CUDA-probe fallback.
- GET `/asr/config`: moved to `app/api/audio.py` in PR4.56; provider fallback returns unavailable config without probing or loading.
- GET `/api/tts/style-bert-vits2/models`: moved to `app/api/audio.py` in PR4.56; fallback avoids heavy filesystem scans.
- POST `/api/tts/style-bert-vits2/preview-normalization`: moved to `app/api/audio.py` in PR4.56; existing LLM fallback remains provider-gated in production and `create_app()` does not call LLM.

### Medium-risk write candidates

- POST `/voice/load`: explicit ASR runtime load.
- POST `/api/tts/style-bert-vits2/prepare`: explicit SBV2/TTS runtime prepare.
- DELETE `/echo/sessions/{filename:path}`: filesystem delete.
- POST `/api/tts/style-bert-vits2/models/upload`: filesystem/model import write.

### High-risk execution candidates

- WebSocket `/echo/stream`: high-risk execution/websocket and last move candidate.
- POST `/voice/transcribe`: high-risk ASR execution.
- POST `/tts/synthesize`: high-risk TTS/SBV2 execution; PR4.57 service body is extracted but route owner remains `main.py`.
- POST `/tts/synthesize-batch`: high-risk batch TTS/SBV2 execution.

## Next PR sequence

- PR4.55: Extract ASR/TTS service functions without moving routes.
- PR4.56: Moved low-risk audio read/status/config routes to `app/api/audio.py` with provider-backed production behavior and safe `create_app()` fallbacks.
- PR4.57: Extracted the POST `/tts/synthesize` non-streaming service body with injected dependencies; route owner remains `main.py`.
- PR4.58+: Move Echo WebSocket last.


### PR4.56 route ownership

- `/voice/status` -> `app/api/audio.py`
- `/asr/config` -> `app/api/audio.py`
- `/audio/runtime/debug` -> `app/api/audio.py`
- `/api/tts/style-bert-vits2/models` -> `app/api/audio.py`
- `/api/tts/style-bert-vits2/preview-normalization` -> `app/api/audio.py`
- Execution/high-risk routes remain `main.py`: `/voice/load`, `/voice/transcribe`, `/tts/synthesize`, `/tts/synthesize-batch`, `/api/tts/style-bert-vits2/prepare`, and WebSocket `/echo/stream`.
