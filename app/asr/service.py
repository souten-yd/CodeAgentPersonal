import os
from typing import Callable

from app.env_detection import detect_gpu_profile, detect_os_profile, detect_runpod
from app.asr.whisper_cpp_runtime import resolve_ffmpeg_binary, resolve_whisper_cpp_binary, resolve_whisper_cpp_model, transcribe_with_whisper_cpp


class ASRConfigurationError(RuntimeError):
    pass


def _normalize_asr_engine(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "faster-whisper": "faster_whisper",
        "fasterwhisper": "faster_whisper",
        "whisper.cpp": "whisper_cpp",
        "whisper-cpp": "whisper_cpp",
        "whispercpp": "whisper_cpp",
        "cpp": "whisper_cpp",
    }
    normalized = aliases.get(raw, raw)
    if normalized in {"faster_whisper", "whisper_cpp", "auto"}:
        return normalized
    return "faster_whisper"


def _engine_setting() -> str:
    raw = os.environ.get("CODEAGENT_ASR_ENGINE")
    if raw is None or str(raw).strip() == "":
        return "auto"
    return _normalize_asr_engine(raw)


def whisper_cpp_ready() -> bool:
    bin_path = resolve_whisper_cpp_binary()
    model_path = resolve_whisper_cpp_model()
    return bool(bin_path and model_path.exists())


def resolve_effective_asr_config() -> dict:
    is_runpod = bool(detect_runpod())
    if is_runpod:
        return {
            "runtime": "runpod",
            "is_windows": False,
            "is_runpod": True,
            "gpu_vendor": "nvidia",
            "effective_engine": "faster_whisper",
            "effective_backend": "cuda",
            "model": "large-v3-turbo",
            "whisper_cpp_visible": False,
            "whisper_cpp_ready": False,
            "whisper_cpp_binary": "",
            "whisper_cpp_model": "",
            "ffmpeg_available": bool(resolve_ffmpeg_binary()),
            "ffmpeg_binary": str(resolve_ffmpeg_binary() or ""),
            "warnings": [],
        }
    os_profile = detect_os_profile()
    gpu = detect_gpu_profile()
    is_windows = bool(os_profile.get("is_windows"))
    is_linux = bool(os_profile.get("is_linux"))
    vendor = str(gpu.get("vendor") or "unknown").lower()
    requested = _engine_setting()
    if requested == "auto":
        requested = ""
    warnings: list[str] = []
    cpp_bin = resolve_whisper_cpp_binary()
    cpp_model = resolve_whisper_cpp_model()
    cpp_assets_ready = whisper_cpp_ready()
    ffmpeg_bin = resolve_ffmpeg_binary()
    ffmpeg_available = bool(ffmpeg_bin)

    effective_engine = "faster_whisper"
    effective_backend = "cpu"
    model = "large-v3-turbo"
    whisper_cpp_visible = bool(is_windows and not is_runpod)
    whisper_cpp_ready_effective = False

    if is_runpod:
        effective_backend = "cuda"
    elif requested == "whisper_cpp":
        if is_windows and vendor == "amd" and cpp_assets_ready and ffmpeg_available:
            effective_engine, effective_backend, model = "whisper_cpp", "vulkan", cpp_model.name
            whisper_cpp_ready_effective = True
        else:
            warnings.append("Run setup_whisper_cpp_vulkan_windows.bat -Force")
            if not ffmpeg_available:
                warnings.insert(0, "ffmpeg is required for browser-recorded webm input")
            else:
                warnings.insert(0, "whisper.cpp Vulkan is not ready.")
    elif requested == "faster_whisper":
        effective_backend = "cuda" if (is_linux and vendor == "nvidia") else "cpu"
    elif is_windows and vendor == "amd" and cpp_assets_ready and ffmpeg_available:
        effective_engine, effective_backend, model = "whisper_cpp", "vulkan", cpp_model.name
        whisper_cpp_ready_effective = True
    elif is_windows and vendor == "amd":
        warnings.append("Run setup_whisper_cpp_vulkan_windows.bat -Force")
        if not ffmpeg_available:
            warnings.insert(0, "ffmpeg is required for browser-recorded webm input")
        else:
            warnings.insert(0, "whisper.cpp Vulkan is not ready.")
    elif is_linux and vendor == "nvidia":
        effective_backend = "cuda"

    return {
        "runtime": "runpod" if is_runpod else ("windows" if is_windows else "linux" if is_linux else "other"),
        "is_windows": is_windows,
        "is_runpod": is_runpod,
        "gpu_vendor": vendor,
        "effective_engine": effective_engine,
        "effective_backend": effective_backend,
        "model": model,
        "whisper_cpp_visible": whisper_cpp_visible,
        "whisper_cpp_ready": whisper_cpp_ready_effective,
        "whisper_cpp_binary": str(cpp_bin) if cpp_bin else "",
        "whisper_cpp_model": str(cpp_model),
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_binary": str(ffmpeg_bin) if ffmpeg_bin else "",
        "warnings": warnings,
    }


def select_asr_backend() -> str:
    mode = _engine_setting()
    cfg = resolve_effective_asr_config()
    if mode == "whisper_cpp" and cfg["effective_engine"] != "whisper_cpp":
        raise ASRConfigurationError("CODEAGENT_ASR_ENGINE=whisper_cpp was requested, but runtime requirements are missing")
    return str(cfg["effective_engine"])


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
