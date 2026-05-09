# PR4.61/PR4.62 ASR transcribe runtime inventory

PR4.61 froze the seam around `POST /voice/transcribe` before extraction. PR4.62 extracts the POST `/voice/transcribe` service body into `app/services/audio_runtime.py` while keeping the route owner in `main.py`; no route move to `app/api/audio.py` is allowed in this PR.

## Current route ownership and scope

- Route: `POST /voice/transcribe`
- Handler: `voice_transcribe_api(req: dict)`
- Route owner: `main.py`
- Execution owner: `app/services/audio_runtime.py` via `run_voice_transcribe_service_body(...)`; the lower-level ASR model helper remains injected from `main.py` to preserve load timing and CUDA fallback.
- Extraction status: service body extracted in PR4.62 with `VoiceTranscribeServiceDependencies` and `VoiceTranscribeServiceResponse`.
- Related high-risk route left untouched: WebSocket `/echo/stream` remains owned by `main.py` and must be extracted last.

## Current processing flow

1. `voice_transcribe_api` accepts a JSON request dictionary, assembles `VoiceTranscribeServiceDependencies`, and delegates to `run_voice_transcribe_service_body(...)`.
2. Missing `audio_base64` raises HTTP 400 with detail `audio_base64 required` before streaming starts.
3. The extracted service body normalizes request fields such as `language`, `model`, `audio_format`, `asr_profile`, beam/search thresholds, and `asr_post_filter`.
4. `_apply_asr_runtime_settings(req)` applies ASR engine/device/compute settings from persisted settings, runtime config, environment, and request override fields.
5. The extracted service body base64-decodes audio bytes. Invalid base64 raises HTTP 400 with detail prefixed by `invalid audio_base64:`.
6. `main.py` maps `AudioRuntimeHttpError` to `HTTPException` and wraps the service response iterator in a `StreamingResponse` with `text/event-stream` media type.
7. If the selected faster-whisper model does not exist locally, the stream first emits a `type=downloading` Server-Sent Event.
8. The stream emits a `type=transcribing` Server-Sent Event.
9. The stream calls `voice_transcribe(...)`, which delegates to `asr_service_transcribe_audio(...)` and the injected `_faster_whisper_transcribe(...)` callback.
10. `_faster_whisper_transcribe(...)` calls `voice_load(model_name=...)`, writes the uploaded bytes to a temporary file, calls `_voice_model.transcribe(temp_path, language=..., **transcribe_kwargs)`, materializes faster-whisper `segments`, joins segment text, builds metrics, may retry once for repetition-loop rejection, and deletes the temporary file in `finally`.
11. The stream emits a final `type=result` event containing the current result payload, or a `type=error` event with `detail=voice transcribe failed: ...` if an exception occurs inside the streaming body.

## Inputs

Current route input is JSON, not multipart upload and not raw request bytes.

| Field | Current behavior |
| --- | --- |
| `audio_base64` | Required JSON string. It is stripped and decoded with `base64.b64decode`. |
| `audio_format` | Optional string. Default `webm`. Used only to derive the temporary file suffix after non-alphanumeric characters are removed. |
| `language` | Optional string. Default `auto`; accepted route values are `auto`, `ja`, `en`. Anything else falls back to `auto`. `_faster_whisper_transcribe` passes `None` to faster-whisper for `auto`. |
| `model` | Optional string. Default `large-v3-turbo`. Passed to `voice_load` / faster-whisper model selection. |
| `device` | Optional. Only honored by `_apply_asr_runtime_settings` when `asr_override` is truthy. Valid values normalize to `cpu` or `cuda`. |
| `compute_type` / `asr_compute_type` | Optional. Only honored by `_apply_asr_runtime_settings` when `asr_override` is truthy. Valid values are `float16`, `int8_float16`, and `int8`; invalid values fall back to device defaults. |
| `asr_engine` | Optional override input; Runpod forces `faster_whisper`. |
| `whisper_cpp_backend` | Optional override input kept in runtime settings, although this route currently uses faster-whisper. |
| `asr_profile` | Optional. Resolved by `_resolve_asr_profile`; controls preset beam/search thresholds. |
| `beam_size` | Optional integer. Invalid values become `None` and then preset defaults are used. |
| `best_of` | Optional integer. Invalid values become `None` and then preset defaults are used. |
| `no_speech_threshold` | Optional float. Invalid values become `None`. |
| `log_prob_threshold` | Optional float. Invalid values become `None`. |
| `compression_ratio_threshold` | Optional float. Invalid values become `None`. |
| `asr_post_filter` | Optional object. Non-dict values are replaced with `{}` at the route seam. |

### MIME, sample rate, and channels

The current JSON route does not inspect MIME type, sample rate, or channel count. It only writes decoded bytes to a temporary file with a suffix derived from `audio_format`; media probing/decoding is left to faster-whisper/ffmpeg through the model transcribe call.

### Task, VAD, silence, and decode options

- No explicit Whisper `task` input is passed by the route today.
- `_build_asr_transcribe_kwargs` always sets `temperature=0.0`, `condition_on_previous_text=False`, `vad_filter=True`, and `word_timestamps=False`.
- Silence/no-speech behavior is controlled by optional `no_speech_threshold` plus post-filter metrics.
- Beam/search options are `beam_size` and `best_of`, with optional thresholds for no-speech, log-probability, and compression ratio.

## Outputs

The route is SSE-based. Stable events are:

- `type=downloading` with `message`, only when the selected model is not cached.
- `type=transcribing` with `message` before ASR execution.
- `type=result` plus the current transcribe result payload on success.
- `type=error` with `detail` on streaming-body failure.

Current success payload fields produced by `_faster_whisper_transcribe` are:

| Field | Meaning |
| --- | --- |
| `text` | Joined and stripped text from faster-whisper segments. Empty string when the repetition post-filter rejects output. |
| `language` | `info.language` from faster-whisper when present, otherwise the requested language. |
| `duration` | `info.duration` from faster-whisper when present, otherwise `0.0`. |
| `model` | Loaded ASR model from `voice_load` status. |
| `auto_unloaded` | Current route passes `False`; model remains resident. |
| `asr_profile` | Resolved ASR profile. |
| `post_filter` | Object containing `enabled`, `rejected`, `reject_reason`, and `retry_applied`. |
| `asr_params` | Effective `beam_size`, `best_of`, `no_speech_threshold`, `log_prob_threshold`, and `compression_ratio_threshold`. |
| `metrics` | Segment-derived metrics: segment count, no-speech probability stats, and average log-probability stats. |

`segments` are created internally by faster-whisper and are consumed for text/metrics. The current route does **not** expose a per-segment list in the response payload; PR4.62 must preserve this current response shape unless a later explicit API-change PR adds `segments`.

## Error payload shape

- Pre-stream validation errors use FastAPI `HTTPException` JSON detail:
  - Missing audio: HTTP 400, `detail="audio_base64 required"`.
  - Invalid base64: HTTP 400, `detail` starts with `invalid audio_base64:`.
- In-stream execution errors are emitted as SSE:
  - `type="error"`
  - `detail="voice transcribe failed: ..."`
- Model-load failures, faster-whisper failures, temporary-file failures, CUDA failures after CPU fallback has failed, and post-filter/runtime failures all currently converge through the in-stream `type=error` payload unless raised before the stream is returned.

## Dependencies and global state

- Loaded ASR model global: `_voice_model`.
- Model metadata globals: `_voice_model_name`, `_voice_model_device`, `_voice_model_compute_type`, `_voice_device`, `_voice_compute_type`.
- CUDA fallback globals: `_last_asr_cuda_error`, `_last_asr_cuda_error_at`.
- Shared lock: `_voice_lock` protects model load and transcribe calls.
- ASR load helper: `voice_load(...)` / `get_or_load_asr_model(...)`.
- Runtime config: `resolve_effective_asr_config()` through `_resolve_asr_runtime_config()` and `_apply_asr_runtime_settings(...)`.
- Runtime detection: `detect_audio_runtime()` is only reached lazily through runtime config helpers; it must not run at import time.
- Audio bytes/temp file helper: `tempfile.NamedTemporaryFile(delete=False)` inside `_faster_whisper_transcribe`, followed by `os.remove(temp_path)` in `finally`.
- Audio decode/transcribe backend: faster-whisper `WhisperModel.transcribe`, backed by ctranslate2 and its ffmpeg/audio decode path.
- Debug/status surface: `/voice/status`, `/asr/config`, `/audio/runtime/debug`, `/runtime/cuda-debug`, `_last_asr_cuda_error`, `_last_asr_cuda_error_at`, route logs, and repetition rejection logs.
- Route-neutral PR4.61 seam types/helpers: `VoiceTranscribeInput`, `VoiceTranscribeResult`, `VoiceTranscribeDiagnostics`, `VoiceTranscribeServicePlan`, `normalize_voice_transcribe_error`, `summarize_voice_transcribe_result`, and `classify_voice_transcribe_failure` in `app/services/audio_runtime.py`.

## CUDA fallback contract

### cuda/float16 success path

1. `_apply_asr_runtime_settings` resolves or preserves `CODEAGENT_ASR_DEVICE=cuda` and `CODEAGENT_ASR_COMPUTE_TYPE=float16` when CUDA is selected.
2. `get_or_load_asr_model` constructs `WhisperModel(..., device="cuda", compute_type="float16", ...)`.
3. `_voice_model_device` and `_voice_model_compute_type` are recorded from the successful load status.
4. Transcribe proceeds through `_voice_model.transcribe(...)` with the current temporary file and kwargs.

### cuda failure -> cpu-int8 fallback

1. If `WhisperModel` construction fails while `_voice_device == "cuda"`, `_record_asr_cuda_error(e)` records the degraded reason details in `_last_asr_cuda_error` and `_last_asr_cuda_error_at`.
2. A warning is logged: ASR CUDA initialization failed and is falling back to CPU/int8.
3. `_asr_fallback_to_cpu()` clears the cached model, sets `_voice_device="cpu"`, `_voice_compute_type="int8"`, and writes `CODEAGENT_ASR_DEVICE=cpu` and `CODEAGENT_ASR_COMPUTE_TYPE=int8`.
4. `WhisperModel` is constructed again with `device="cpu"` and `compute_type="int8"`.
5. The degraded reason to preserve for docs/tests is: CUDA initialization failure caused cpu-int8 fallback. In PR4.61 helper terminology this is `asr_cuda_init_failed_cpu_int8_fallback`.

PR4.62 preserves CUDA fallback, cpu-int8 fallback, degraded reason visibility, and the existing model-load/fallback/transcribe call order through injected production callables.

## Echo `/echo/stream` shared points

- Echo uses ASR transcribe helpers from `main.py` and therefore shares `_voice_model`, `_voice_lock`, model selection, CUDA fallback globals, runtime settings, and the faster-whisper model cache.
- Echo WebSocket `/echo/stream` remains a separate high-risk execution route owned by `main.py`.
- This PR does not touch Echo session write/delete, WebSocket behavior, Echo audio buffering, or Echo ASR reuse logic.
- PR4.63 should stabilize Echo stream ASR reuse seams after `/voice/transcribe` service extraction.
- PR4.64+ should extract Echo WebSocket last.

## PR4.62 service extraction boundary

PR4.62 extracts the route-neutral service body around:

- request normalization after `req` arrives;
- base64 decode and temporary-file orchestration;
- calls to injected ASR load/transcribe dependencies;
- transcribe kwargs construction and post-filter shaping;
- success/error payload shaping for the existing SSE event contract.

PR4.62 injects dependencies explicitly and keeps the route owner as `main.py`.

## Do not touch in PR4.61/PR4.62 without a dedicated plan

- Do not move `POST /voice/transcribe` out of `main.py`.
- Do not move WebSocket `/echo/stream`.
- Do not change faster-whisper call order.
- Do not change CUDA fallback or cpu-int8 fallback behavior.
- Do not change response shape, error shape, temporary-file behavior, or audio decode assumptions.
- Do not change model auto-load/switch, Runpod CUDA/llama NGL probing, TTS, SBV2, Nexus, Jobs, Lumen, UI, or Dockerfile behavior.


## PR4.62 extraction note

- PR4.62 moved the POST `/voice/transcribe` request normalization, base64 bytes handling, SSE event shaping, transcribe callable invocation, stream error event handling, and response metadata into `app/services/audio_runtime.py`.
- Route owner remains `main.py`; `main.py` still owns `@app.post("/voice/transcribe")`, production dependency assembly, and `AudioRuntimeHttpError` to `HTTPException` mapping.
- `/voice/load` and `/voice/transcribe` now have service bodies extracted while preserving ASR model load timing through injected production callables.
- CUDA success and CUDA failure CPU/int8 fallback behavior remain in the injected lower-level ASR load/transcribe helpers.
- WebSocket `/echo/stream` remains in `main.py`; Echo stream extraction is intentionally last after PR4.63 stabilizes the ASR reuse seam.
