# PR4.50.1 CUDA regression trace from KasaneCore_v2.7

## Baseline and scope

- Normal baseline: `KasaneCore_v2.7`.
- Local comparison anchor: commit `832c5b5` (`Merge pull request #949 ... document-runtime-control-endpoint-inventory`).  The local repository does not contain a tag or branch literally named `KasaneCore_v2.7`, but `832c5b5..HEAD` is 26 commits ahead and matches the reported router/service split window.
- Investigation focus: Python import order, router split side effects, provider registration, and startup/runtime probe timing.
- Out of scope for this PR: Dockerfile rewrites, model asset rewrites, Nexus execution service extraction, `POST /jobs/submit` behavior changes, ASR/TTS inference changes, and large ModelManager search rewrites.

## File-level diff inventory for CUDA-impact candidates

`git diff --name-status 832c5b5..HEAD -- <candidate paths>` shows these changed files in the requested CUDA-impact set:

| Path | Status since baseline | CUDA regression relevance |
| --- | --- | --- |
| `app/server.py` | Modified | App factory router inclusion expanded after v2.7. This PR keeps `app.server` import safe by moving split-router imports into `include_routers(app)` so merely importing the factory module cannot import routers with future runtime side effects. |
| `main.py` | Modified | Main now delegates many routes through routers/providers. This PR removes the import-time `detect_audio_runtime()` call from ASR globals so `main:app` import does not call `torch.cuda.is_available()` / `ctranslate2` before an explicit ASR/runtime debug operation. |
| `app/api/runtime_controls.py` | Added | Router fallback payloads are provider-based and side-effect free. This PR extends `/runtime/cuda-debug` fallback shape with v2.7 baseline metadata and no live CUDA probe. |
| `app/api/echo.py` | Added | Router uses providers and fallback payloads only; import does not load ASR/TTS runtime or scan EchoVault storage. |
| `app/api/jobs.py` | Added | Router uses providers and fallback payloads only; import does not touch LLM, CUDA, ModelManager, or job execution. |
| `app/api/nexus.py` | Added | Router uses providers and fallback payloads only; import does not probe SearXNG, LLM, CUDA, Nexus storage, or active jobs. |
| `app/services/jobs.py` | Added | Job execution extraction exists in the diff window, but this PR does not change execution logic. |
| `app/audio/runtime_config.py` | Unchanged in this comparison | The CUDA selection/probe code itself is not the apparent diff; the risk is when `detect_audio_runtime()` is called. |
| `app/asr/service.py` | Unchanged in this comparison | ASR service still calls `detect_audio_runtime()` during ASR config resolution/transcription paths, not at router import time. |
| `app/tts/style_bert_vits2_runtime.py` | Unchanged in this comparison | SBV2 runtime status/synthesis paths can probe torch when explicitly called, but router imports should not call those paths. |

## Docker / launcher / entrypoint / run-script diff inventory

The same comparison did **not** show changes to Docker/build/runtime image files in this regression window:

- `Dockerfile`: no diff in `832c5b5..HEAD` for the candidate comparison.
- `docker/start-services.sh`: no diff in `832c5b5..HEAD` for the candidate comparison.
- `setup_whisper_cpp_vulkan_windows.bat`: no diff in `832c5b5..HEAD` for the candidate comparison.
- `setup_style_bert_vits2_windows.bat`: no diff in `832c5b5..HEAD` for the candidate comparison.
- `DLllama.bat`: no diff in `832c5b5..HEAD` for the candidate comparison.

Conclusion: the first suspect remains Python startup/import/provider timing, not Docker image construction.

## Runtime probe timing audit

- `app.server` previously imported all split routers at module top level.  That made production `main.py` import those factory routers immediately because `main.py` imports `include_routers`.  This PR changes `app.server` so router imports happen inside `include_routers(app)`.
- `main.py` had top-level ASR globals initialized by `detect_audio_runtime()`.  Since `detect_audio_runtime()` calls torch CUDA and ctranslate2 CUDA probes, this was an import-time CUDA probe during `uvicorn main:app` import.  This PR makes ASR device/compute selection lazy and reports `uninitialized` in `voice_status()` until ASR is explicitly loaded/transcribed.
- `/runtime/cuda-debug` is intentionally an explicit diagnostic endpoint.  It may probe torch/ctranslate2 when requested, and now reports v2.7 baseline metadata plus torch, ctranslate2, and llama validation fields.
- `/audio/runtime/debug` remains an explicit audio diagnostic endpoint and may probe audio/TTS runtimes when requested.  It is not called by router import or `create_app()` fallback registration.

## CUDA_VISIBLE_DEVICES mutation audit

Repository search for `CUDA_VISIBLE_DEVICES` in the affected Python/runtime files found reads in `app/audio/runtime_config.py` and no new writes to `os.environ["CUDA_VISIBLE_DEVICES"]` in the v2.7-to-main router/service split window.  No launcher/Docker diff was present in this comparison window.

Existing runtime code still writes ASR-specific environment overrides (`CODEAGENT_ASR_DEVICE`, `CODEAGENT_ASR_COMPUTE_TYPE`) only when ASR CUDA initialization fails and falls back to CPU; this PR does not change that inference behavior.

## Diagnostic fields added to `/runtime/cuda-debug`

The runtime CUDA debug payload now includes:

- `baseline_ref: "KasaneCore_v2.7"`
- `changed_since_baseline: true`
- `suspected_changed_files`
- `import_time_probe_detected`
- `torch_cuda_available`
- `torch_cuda_error`
- `ctranslate2_cuda_available`
- `ctranslate2_cuda_error`
- `llama_cuda_validation_reason`

These fields are present both in provider-less app-factory fallback responses and in production `main.app` provider responses.

## Runpod commands to paste after deploy

```bash
curl -s http://127.0.0.1:8000/runtime/cuda-debug | python -m json.tool
curl -s http://127.0.0.1:8000/models/db/status | python -m json.tool
curl -s http://127.0.0.1:8000/audio/runtime/debug | python -m json.tool
```

```bash
/opt/venv/bin/python - <<'PY'
import os
print("CUDA_VISIBLE_DEVICES=", os.environ.get("CUDA_VISIBLE_DEVICES"))
print("NVIDIA_VISIBLE_DEVICES=", os.environ.get("NVIDIA_VISIBLE_DEVICES"))
try:
    import torch
    print("torch", torch.__version__)
    print("torch.version.cuda", torch.version.cuda)
    print("torch.cuda.is_available", torch.cuda.is_available())
    print("torch.cuda.device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("torch.cuda.device_name", torch.cuda.get_device_name(0))
except Exception as e:
    print("torch error:", repr(e))
try:
    import ctranslate2
    print("ctranslate2", ctranslate2.__version__)
    print("ct2 cuda devices", ctranslate2.get_cuda_device_count())
    print("ct2 cuda compute types", ctranslate2.get_supported_compute_types("cuda"))
except Exception as e:
    print("ctranslate2 error:", repr(e))
PY
```
