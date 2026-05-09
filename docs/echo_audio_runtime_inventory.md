# PR4.54 Echo / ASR / TTS / SBV2 runtime boundary inventory

PR4.54 is a preparation-only PR after the healthy `KasaneCore_v2.8` baseline.  `KasaneCore_v2.8 == main at e94c20dfe0d23e233f4dbc817af994408e739b80` remains the recovery point where LLM / ASR / TTS / Nexus / Lumen were confirmed healthy, including ASR OK and TTS/SBV2 OK.  This inventory does **not** move routes, change runtime behavior, start model loads, or run CUDA probes at import time.

## Guardrails

- Keep every Echo / ASR / TTS / SBV2 execution route owner unchanged in `main.py` for this PR.
- Do not call `detect_audio_runtime()` at import time.
- Do not import `torch`, `ctranslate2`, `faster_whisper`, or Style-Bert-VITS2 runtime modules from `app/services/audio_runtime.py` at module import time.
- Do not change WebSocket `/echo/stream`, POST `/voice/transcribe`, POST `/tts/synthesize`, POST `/tts/synthesize-batch`, SBV2 normalization, dictionary cache, katakana fallback, LLM fallback, model auto-load, or Runpod CUDA / llama NGL probing.
- `create_app()` fallbacks must remain safe: no CUDA probe, no ASR/TTS model load, no SBV2 runtime prepare, no filesystem-heavy scan, and no LLM fallback generation.

## Endpoint inventory

| Risk | Endpoint / feature | Current owner module | Related helpers / global state | Runtime load | CUDA probe | Filesystem write | LLM fallback | create_app fallback note | Move classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low-risk read/status | GET `/voice/status` | `main.py` | `voice_status()`, ASR runtime globals/status fields | No intentional load | Must not probe; status-only | No | No | Needs safe static/provider fallback before route move | Move candidate in PR4.56 after service seams |
| medium-risk write/runtime-load | POST `/voice/load` | `main.py` | `_apply_asr_runtime_settings()`, `voice_load()`, ASR model manager | Yes, ASR runtime load | May use selected ASR device only during explicit load | No direct user file write | No | Fallback should report unavailable, not load | Keep in `main.py` until helper extraction |
| high-risk execution | POST `/voice/transcribe` | `main.py` | `_apply_asr_runtime_settings()`, `_resolve_asr_profile()`, ASR decode/transcribe helpers, audio temp handling | May load/keep ASR model resident | CUDA/device behavior only during explicit transcription/load | Temporary audio decode/write path may be used | Post-filter path must stay unchanged | Fallback should reject without ASR execution | Do not move before PR4.55 helper contracts |
| low-risk read/status | GET `/asr/config` | `main.py` | `_resolve_asr_runtime_config()`, `app/audio/runtime_config.py` configuration shape | No model load | Must not call heavy CUDA probe from fallback/import | No | No | Safe provider/static fallback needed | Move candidate in PR4.56 |
| high-risk execution/websocket | WebSocket `/echo/stream` | `main.py` | `_echo_sessions`, `_echo_debug_append()`, `_echo_save_lock`, `_echo_minutes_lock`, ASR chunk handling, TTS response flow | Can invoke ASR/TTS runtime during live session | Device/runtime behavior during explicit stream execution | Writes EchoVault sessions/debug/minutes | Possible through downstream response generation paths; keep unchanged | No WebSocket fallback until dedicated route plan | Move last in PR4.58+ |
| medium-risk write/filesystem | DELETE `/echo/sessions/{filename:path}` | `main.py` | `ECHOVAULT_DIR`, Echo session path sanitizer, session providers | No | No | Deletes EchoVault files | No | Needs provider fallback and path-safety contract | Move only after write seam is explicit |
| medium-risk write/runtime-load | POST `/api/tts/style-bert-vits2/prepare` | `main.py` | `_style_bert_vits2_init_lock`, `_tts_engine_registry`, `_STYLE_BERT_VITS2_*`, SBV2 prepare helpers | Yes, SBV2/TTS runtime prepare | Device choice may touch CUDA during explicit prepare | May initialize/download/prepare local runtime artifacts | No direct preview fallback | Fallback must not initialize runtime | Keep in `main.py` until SBV2 seam is explicit |
| low-risk read/status | GET `/api/tts/style-bert-vits2/models` | `main.py` | `_style_bert_vits2_list_models()`, `_style_bert_vits2_describe_model()` | No | No | No | No | Fallback can be empty/static if it avoids heavy scans | Candidate after filesystem rules are fixed |
| low/medium-risk read-preview with LLM fallback caution | POST `/api/tts/style-bert-vits2/preview-normalization` | `main.py` | `_tts_engine_registry`, `StyleBertVITS2Runtime.build_normalization_preview()`, normalization, katakana fallback, dictionary cache | No model load intended, but runtime object required | No import-time probe; runtime may already know device | May read/write dictionary/cache depending existing runtime behavior | **Yes/caution** if normalization path asks LLM fallback | Fallback must not invoke LLM or SBV2 runtime | Move only after LLM fallback is contract-tested |
| medium-risk write/filesystem | POST `/api/tts/style-bert-vits2/models/upload` | `main.py` | `import_model_zip()`, `_STYLE_BERT_VITS2_MODELS_DIR`, model list helpers | No TTS synthesis, but changes model inventory | No | Uploads/imports SBV2 model zip | No | Fallback should reject unavailable without writing | Not part of first low-risk move |
| high-risk execution | POST `/tts/synthesize` | `main.py` | `_tts_engine_registry`, `StyleBertVITS2Runtime`, `_write_tts_debug_entry()`, ref audio helpers, normalization pipeline | Can prepare/load/use TTS/SBV2 runtime | Device/runtime behavior during explicit synthesis | Writes debug/ref/temp/output artifacts | Possible through SBV2 text normalization fallback path; keep unchanged | Fallback should reject without synthesis | Do not move before PR4.55 helper contracts |
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

- GET `/voice/status`: low-risk read/status, but still `main.py` until PR4.56 because it reports live ASR state and must preserve the no-CUDA-probe invariant.
- GET `/asr/config`: low-risk read/status, but still `main.py` until a provider fallback can return configuration without probing or loading.
- GET `/api/tts/style-bert-vits2/models`: low-risk read/status if the fallback can avoid heavy filesystem scans.
- POST `/api/tts/style-bert-vits2/preview-normalization`: only low/medium risk when LLM fallback is disabled or safely provider-gated; otherwise caution.

### Medium-risk write candidates

- POST `/voice/load`: explicit ASR runtime load.
- POST `/api/tts/style-bert-vits2/prepare`: explicit SBV2/TTS runtime prepare.
- DELETE `/echo/sessions/{filename:path}`: filesystem delete.
- POST `/api/tts/style-bert-vits2/models/upload`: filesystem/model import write.

### High-risk execution candidates

- WebSocket `/echo/stream`: high-risk execution/websocket and last move candidate.
- POST `/voice/transcribe`: high-risk ASR execution.
- POST `/tts/synthesize`: high-risk TTS/SBV2 execution.
- POST `/tts/synthesize-batch`: high-risk batch TTS/SBV2 execution.

## Next PR sequence

- PR4.55: Extract ASR/TTS service functions without moving routes.
- PR4.56: Move low-risk audio status/config routes if provider fallbacks are safe.
- PR4.57: Move TTS/SBV2 non-streaming routes only if runtime, filesystem, and LLM fallback seams are proven safe.
- PR4.58+: Move Echo WebSocket last.
