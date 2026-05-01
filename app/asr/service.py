import os
from typing import Callable

from app.env_detection import detect_gpu_profile, detect_os_profile, detect_runpod
from app.asr.whisper_cpp_runtime import resolve_whisper_cpp_binary, resolve_whisper_cpp_model, transcribe_with_whisper_cpp


class ASRConfigurationError(RuntimeError):
    pass


def _engine_setting() -> str:
    raw = (os.environ.get("CODEAGENT_ASR_ENGINE") or "").strip().lower()
    if raw in {"faster_whisper", "whisper_cpp", "auto"}:
        return raw
    return "faster_whisper"


def whisper_cpp_ready() -> bool:
    bin_path = resolve_whisper_cpp_binary()
    model_path = resolve_whisper_cpp_model()
    return bool(bin_path and model_path.exists())


def select_asr_backend() -> str:
    mode = _engine_setting()
    if mode == "faster_whisper":
        return "faster_whisper"
    if mode == "whisper_cpp":
        if not whisper_cpp_ready():
            raise ASRConfigurationError("CODEAGENT_ASR_ENGINE=whisper_cpp was requested, but binary/model is missing")
        return "whisper_cpp"
    # auto
    if detect_runpod():
        return "faster_whisper"
    os_profile = detect_os_profile()
    gpu = detect_gpu_profile()
    if os_profile.is_linux and gpu.vendor == "nvidia":
        return "faster_whisper"
    if os_profile.is_windows and gpu.vendor == "amd" and whisper_cpp_ready():
        return "whisper_cpp"
    return "faster_whisper"


def transcribe_audio(
    audio_bytes: bytes,
    language: str,
    model_name: str,
    audio_format: str,
    faster_whisper_transcribe: Callable[..., dict],
    **kwargs,
) -> dict:
    backend = select_asr_backend()
    if backend == "whisper_cpp":
        return transcribe_with_whisper_cpp(audio_bytes=audio_bytes, audio_format=audio_format, language=language)
    return faster_whisper_transcribe(
        audio_bytes=audio_bytes,
        language=language,
        model_name=model_name,
        audio_format=audio_format,
        **kwargs,
    )
