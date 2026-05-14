from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

DEFAULT_SBV2_MODEL = "koharune-ami"
DEFAULT_TTS_ENGINE = "style_bert_vits2"


@dataclass(frozen=True)
class Sbv2RuntimePolicy:
    engine: str = DEFAULT_TTS_ENGINE
    default_model: str = DEFAULT_SBV2_MODEL
    device: str = "auto"
    prefer_safetensors: bool = True
    allow_onnx: bool = False
    prefer_onnx: bool = False
    force_pytorch_jit_zero: bool = False
    dummy_warmup_enabled: bool = False
    import_time_side_effects_allowed: bool = False
    platform: str = ""
    runtime_profile: str = ""


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _get(env: Mapping[str, str], key: str, default: str = "") -> str:
    return str(env.get(key, default) or "").strip()


def detect_runtime_profile(env: Mapping[str, str], platform: str = "") -> str:
    platform_l = str(platform or "").lower()
    runpod_markers = [
        "RUNPOD_POD_ID",
        "RUNPOD_PUBLIC_IP",
        "RUNPOD_CPU_COUNT",
    ]

    if any(_get(env, key) for key in runpod_markers):
        return "runpod"

    if "linux" in platform_l and (
        _get(env, "NVIDIA_VISIBLE_DEVICES") or _get(env, "CUDA_VISIBLE_DEVICES")
    ):
        return "linux_nvidia"

    if "win" in platform_l:
        return "windows"

    return "generic"


def resolve_sbv2_runtime_policy(
    env: Mapping[str, str] | None = None,
    *,
    platform: str = "",
) -> Sbv2RuntimePolicy:
    env = env or {}
    profile = detect_runtime_profile(env, platform)
    requested_device = (
        _get(env, "STYLE_BERT_VITS2_DEVICE")
        or _get(env, "SBV2_DEVICE")
        or _get(env, "TTS_DEVICE")
        or "auto"
    )

    prefer_safetensors = True
    allow_onnx = profile == "windows" and _truthy(_get(env, "SBV2_ALLOW_ONNX"))
    prefer_onnx = profile == "windows" and _truthy(_get(env, "SBV2_PREFER_ONNX"))
    force_pytorch_jit_zero = False
    dummy_warmup_enabled = _truthy(_get(env, "SBV2_DUMMY_WARMUP"))

    return Sbv2RuntimePolicy(
        engine=DEFAULT_TTS_ENGINE,
        default_model=DEFAULT_SBV2_MODEL,
        device=requested_device,
        prefer_safetensors=prefer_safetensors,
        allow_onnx=allow_onnx,
        prefer_onnx=prefer_onnx,
        force_pytorch_jit_zero=force_pytorch_jit_zero,
        dummy_warmup_enabled=dummy_warmup_enabled,
        import_time_side_effects_allowed=False,
        platform=platform,
        runtime_profile=profile,
    )
