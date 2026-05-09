# Echo stream runtime inventory (PR4.63)

PR4.63 stabilizes the ASR reuse seam for WebSocket `/echo/stream` before any WebSocket extraction. WebSocket `/echo/stream` is a high-risk route, and the route owner is `main.py`; the websocket loop and `echo_stream_ws` execution body intentionally remain in `main.py`.

## Current processing flow

1. `main.py` accepts WebSocket `/echo/stream` in `echo_stream_ws`.
2. The client sends a text `start` message.
3. `echo_stream_ws` initializes Echo session state, ASR options, audio format metadata, translation/TTS options, debug state, and session persistence state.
4. The client sends audio chunks as binary frames or JSON/base64 chunk messages.
5. `echo_stream_ws` resolves the chunk `seq`, `audio_bytes`, `mime`, `audio_format`, `sample_rate`, `channels`, and `session_id` from the active session and incoming message.
6. The route appends audio to the in-memory session buffer, preserving the current PCM-to-WAV/session-buffer behavior.
7. The route sends the existing websocket status payload: `{"type":"status","state":"transcribing"}`.
8. The ASR call site runs `_echo_voice_transcribe(...)` in a worker thread.
9. The route post-processes ASR text with overlap trimming, post-filter rejection, language normalization, translation, Echo session writes, and optional TTS continuation.
10. The route sends the existing websocket message shape: `status`, `ack`, `sentence`, `translation`, `error`, and `ui_log` messages.

## Connection start initialization

On `type == "start"`, `echo_stream_ws` owns these initialization steps:

- `session_id`, `language`, `model_name`, ASR profile and threshold parsing.
- Optional ASR device request handling through the existing `voice_load(...)` path.
- `audio_format`, `sample_rate`, `channels`, and `mime` defaults for subsequent chunks.
- Echo session dictionary creation under `_echo_sessions`.
- Debug entry creation with the current `_echo_debug_append(...)` format.
- Echo session save/minutes state remains connected to the existing `main.py` write path.

## Audio chunk handling

The current chunk boundary is:

- `seq`: preserved for duplicate detection, `ack`, filtered `ack`, error `ack`, and debug entries.
- `audio_bytes`: passed directly into `_echo_voice_transcribe(...)` for the current chunk, while the full session buffer is maintained separately for save/minutes behavior.
- `mime`: retained for debug/error context and severe error summaries.
- `session_id`: retained for `_echo_sessions`, `_echo_debug_append(...)`, error logging, and session save boundaries.
- PCM chunks still update `pcm_buffer` and the WAV session buffer; non-PCM chunks still append to the WebM buffer.

## ASR call site

The ASR call site is inside `echo_stream_ws` after chunk validation and buffer update. It must preserve:

- `asr_start` and `asr_end` debug event names.
- `perf_ms`, `elapsed_ms`, `result_chars`, metrics, and `post_filter` debug fields.
- Worker-thread execution of `_echo_voice_transcribe(...)`.
- The exact websocket message shape around status, rejection, result, and error handling.

## `_echo_voice_transcribe(...)` role

`_echo_voice_transcribe(...)` is the current Echo-specific ASR helper in `main.py`. Its responsibilities are:

- Convert raw PCM chunks to a numpy float buffer when possible, or fall back to WAV bytes.
- Write byte-like audio input to a temporary file with the current suffix behavior.
- Resolve ASR post-filter configuration.
- Use global ASR model state through `get_or_load_asr_model(...)`, `_voice_model`, and `_voice_lock`.
- Reuse `_resolve_asr_profile(...)` and `_build_asr_transcribe_kwargs(...)`.
- Apply the current repetition-loop retry/reject behavior.
- Return `text`, `language`, `duration`, `metrics`, `asr_profile`, and `post_filter`.
- Remove temporary files in `finally`.

## Relationship to POST `/voice/transcribe` service body

POST `/voice/transcribe` has its service body extracted into `app/services/audio_runtime.py`. Echo stream can later reuse compatible ASR pieces from that service seam, especially:

- ASR profile normalization.
- Transcribe argument shaping.
- ASR post-filter and metrics envelopes.
- CUDA fallback / CPU fallback diagnostics around model load/reuse.
- Route-neutral result summaries and normalized error diagnostics.

PR4.63 only adds Echo stream seam types/helpers to `app/services/audio_runtime.py`; it does not create `run_echo_stream_service_body` and does not move WebSocket `/echo/stream`.

## Differences from POST `/voice/transcribe`

Echo stream remains different from POST `/voice/transcribe` in these ways:

- Echo uses a long-lived WebSocket loop and multiple chunk messages; POST `/voice/transcribe` handles a single request body.
- Echo tracks `seq`, duplicate chunks, `ack`, filtered `ack`, and error `ack` websocket messages.
- Echo owns session buffers, `_echo_sessions`, debug logs, save/minutes state, and reconnection/resume state.
- Echo performs overlap trimming and recent prompt handling between chunks.
- Echo continues into translation and optional TTS playback flow after successful ASR.
- Echo error payloads must preserve the websocket message shape, including `{"type":"error","detail":"ASR error: ...","summary":"..."}`, `ui_log`, and `ack` with `error: true` when `seq` is present.

## TTS boundary

TTS playback chain behavior is outside PR4.63. Echo ASR may feed translated text and `tts_text` into downstream TTS behavior, but this PR does not alter TTS engine selection, SBV2 behavior, playback payloads, or `/tts/synthesize` and `/tts/synthesize-batch` routes.

## Echo session save boundary

Echo session write/save/delete behavior remains in `main.py` and existing Echo routers/providers. PR4.63 documents the seam only. Do not change `_echo_sessions`, `_echo_save_lock`, minutes generation state, session JSON shape, or DELETE session behavior.

## Error payload / websocket message shape

The websocket message shape must be maintained:

- Status: `{"type":"status","state":"transcribing"}` and `{"type":"status","state":"recording"}`.
- Skip/filtered acknowledgements: `{"type":"ack","seq":...,"skipped":true,...}` or `{"type":"ack","seq":...,"filtered":true,...}`.
- Successful acknowledgement: `{"type":"ack","seq":...}`.
- ASR error: `{"type":"error","detail":"ASR error: ...","summary":"[Echo重大エラー] ..."}`.
- UI error log: `{"type":"ui_log","level":"error","summary":"[Echo重大エラー] ..."}`.
- Error acknowledgement when `seq` exists: `{"type":"ack","seq":...,"error":true}`.
- Sentence/translation payloads keep their existing text, language, translation, warning, and TTS fields.

## Debug log format

The debug log format remains `_echo_debug_append(...)` entries keyed by `session_id`, `seq`, and `event_type`. Important event types include:

- `ws_send`
- `chunk_empty`
- `chunk_skip_too_small`
- `chunk_receive`
- `asr_start`
- `asr_end`
- `asr_reject`
- `asr_overlap_trim`
- `chunk_done`
- `chunk_error`
- `ack_error`
- `ws_exception`

PR4.63 must preserve field names such as `receive_ts`, `bytes`, `mime`, `perf_ms`, `elapsed_ms`, `result_chars`, `mean_no_speech_prob`, `mean_avg_logprob`, `post_filter`, `error`, and `traceback`.

## CUDA fallback / CPU fallback

Echo stream ASR currently reaches model load/reuse through `get_or_load_asr_model(...)` and optional `voice_load(...)` on start when an ASR device is requested. CUDA fallback and CPU fallback behavior must remain unchanged. `app/services/audio_runtime.py` Echo seam helpers are route-neutral and must not import `torch`, `ctranslate2`, or `faster_whisper` at top level and must not trigger import-time CUDA probes.

## Scope allowed for PR4.64

The next PR may service-ize only the Echo stream ASR helper body around `_echo_voice_transcribe(...)` and route-neutral payload/diagnostic shaping. Allowed candidates:

- Build an Echo ASR input snapshot from `audio_bytes`, `seq`, `mime`, `session_id`, ASR profile, thresholds, and prompt metadata.
- Summarize ASR result metadata for debug logging.
- Normalize ASR error diagnostics while preserving websocket payload shape.
- Move pure ASR helper-body logic behind explicit dependencies, without moving the WebSocket route.

## Scope still forbidden

Do not move or change these areas in PR4.63:

- WebSocket `/echo/stream` route owner.
- `echo_stream_ws` main loop.
- WebSocket message shape.
- Echo session write/save/delete behavior.
- TTS playback chain.
- POST `/voice/load` behavior.
- POST `/voice/transcribe` behavior.
- POST `/tts/synthesize`, POST `/tts/synthesize-batch`, or SBV2 prepare behavior.
- Runpod CUDA / llama NGL probing, model auto-load/switch, Nexus, Jobs, Lumen, UI, or Dockerfile behavior.
