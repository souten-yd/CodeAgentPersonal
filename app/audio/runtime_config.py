from __future__ import annotations

import os
import platform
import shutil
from dataclasses import asdict, dataclass
from typing import Any

from app.env_detection import detect_gpu_profile, detect_os_profile, detect_runpod


@dataclass(frozen=True)
class AudioRuntimeConfig:
    is_runpod: bool
    is_windows: bool
    gpu_vendor: str
    asr_device: str
    asr_compute_type: str
    tts_device: str
    cuda_visible_devices: str
    nvidia_visible_devices: str
    torch_cuda_available_main: bool
    ctranslate2_cuda_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_choice(value: str | None, allowed: set[str], default: str) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in allowed else default


def _torch_cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _ctranslate2_cuda_available() -> bool:
    try:
        import ctranslate2  # type: ignore

        get_count = getattr(ctranslate2, "get_cuda_device_count", None)
        if callable(get_count):
            return int(get_count()) > 0
        get_supported = getattr(ctranslate2, "get_supported_compute_types", None)
        if callable(get_supported):
            return bool(get_supported("cuda"))
    except Exception:
        return False
    return False


def _cuda_visibility_enabled(cuda_visible: str, nvidia_visible: str) -> bool:
    disabled_markers = {"", "-1", "none", "void"}
    return cuda_visible.strip().lower() not in disabled_markers or nvidia_visible.strip().lower() not in disabled_markers


def detect_audio_runtime() -> AudioRuntimeConfig:
    is_runpod = bool(detect_runpod())
    os_profile = detect_os_profile()
    gpu = detect_gpu_profile()
    is_windows = bool(os_profile.get("is_windows")) or platform.system() == "Windows" or os.name == "nt"
    gpu_vendor = str(gpu.get("vendor") or "unknown").strip().lower() or "unknown"
    cuda_visible = str(os.environ.get("CUDA_VISIBLE_DEVICES", ""))
    nvidia_visible = str(os.environ.get("NVIDIA_VISIBLE_DEVICES", ""))
    torch_cuda = _torch_cuda_available()
    ct2_cuda = _ctranslate2_cuda_available()
    has_cuda_hint = (
        is_runpod
        or gpu_vendor == "nvidia"
        or _cuda_visibility_enabled(cuda_visible, nvidia_visible)
        or bool(shutil.which("nvidia-smi"))
        or os.path.isdir("/usr/local/cuda")
        or torch_cuda
        or ct2_cuda
    )

    requested_asr_device = _normalize_choice(os.environ.get("CODEAGENT_ASR_DEVICE"), {"auto", "cuda", "cpu"}, "auto")
    if requested_asr_device == "cuda":
        asr_device = "cuda"
    elif requested_asr_device == "cpu":
        asr_device = "cpu"
    elif is_runpod:
        asr_device = "cuda"
    else:
        asr_device = "cuda" if (not is_windows and has_cuda_hint and gpu_vendor == "nvidia") else "cpu"

    requested_compute = _normalize_choice(
        os.environ.get("CODEAGENT_ASR_COMPUTE_TYPE"),
        {"auto", "float16", "int8_float16", "int8"},
        "auto",
    )
    if requested_compute != "auto":
        asr_compute_type = requested_compute
    elif asr_device == "cuda":
        asr_compute_type = "float16"
    else:
        asr_compute_type = "int8"

    requested_tts = _normalize_choice(
        os.environ.get("CODEAGENT_STYLE_BERT_VITS2_DEVICE"),
        {"auto", "cuda", "cpu", "mps", "directml", "dml"},
        "auto",
    )
    if is_windows and requested_tts in {"", "auto", "cuda", "directml", "dml"}:
        tts_device = "cpu"
    elif requested_tts != "auto":
        tts_device = requested_tts
    elif is_runpod:
        tts_device = "cuda"
    elif not is_windows and (torch_cuda or (gpu_vendor == "nvidia" and has_cuda_hint)):
        tts_device = "cuda"
    else:
        tts_device = "cpu"

    return AudioRuntimeConfig(
        is_runpod=is_runpod,
        is_windows=is_windows,
        gpu_vendor=gpu_vendor,
        asr_device=asr_device,
        asr_compute_type=asr_compute_type,
        tts_device=tts_device,
        cuda_visible_devices=cuda_visible,
        nvidia_visible_devices=nvidia_visible,
        torch_cuda_available_main=torch_cuda,
        ctranslate2_cuda_available=ct2_cuda,
    )
