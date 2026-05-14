# SBV2 Runtime Defaults

## Engine
- TTS engine is Style-Bert-VITS2 only.
- Qwen/Qwen3 TTS is not supported.
- Engine selector UI must not be reintroduced.

## Default model
- Default SBV2 model: `koharune-ami`.
- UI fallback and runtime fallback should use `koharune-ami`.

## Runpod / Linux / NVIDIA
- Prefer safetensors runtime path.
- Do not force `PYTORCH_JIT=0`.
- Do not auto-prefer `.onnx`.
- Do not enable dummy warm-up by default.
- Warm-up must be explicit or controlled by a clearly named env flag.

## Windows
- Windows may use CPU / DirectML / ONNX / Vulkan-adjacent helpers if already supported.
- Dummy warm-up remains default OFF unless explicitly enabled.
- safetensors warm-start path should be supported when available.

## Import-time side effects
- No model load at import time.
- No model download at import time.
- No warm-up at import time.
