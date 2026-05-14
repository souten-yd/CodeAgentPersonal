from pathlib import Path

from app.services.sbv2_runtime_policy import (
    DEFAULT_SBV2_MODEL,
    DEFAULT_TTS_ENGINE,
    resolve_sbv2_runtime_policy,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "app" / "services" / "sbv2_runtime_policy.py"


def test_sbv2_policy_defaults_are_sbv2_only() -> None:
    policy = resolve_sbv2_runtime_policy({}, platform="linux")
    assert DEFAULT_TTS_ENGINE == "style_bert_vits2"
    assert DEFAULT_SBV2_MODEL == "koharune-ami"
    assert policy.engine == "style_bert_vits2"
    assert policy.default_model == "koharune-ami"
    assert policy.prefer_safetensors is True
    assert policy.import_time_side_effects_allowed is False


def test_runpod_does_not_prefer_onnx_or_force_jit_zero() -> None:
    policy = resolve_sbv2_runtime_policy(
        {
            "RUNPOD_POD_ID": "pod",
            "SBV2_ALLOW_ONNX": "1",
            "SBV2_PREFER_ONNX": "1",
            "PYTORCH_JIT": "0",
        },
        platform="linux",
    )
    assert policy.runtime_profile == "runpod"
    assert policy.allow_onnx is False
    assert policy.prefer_onnx is False
    assert policy.force_pytorch_jit_zero is False


def test_windows_can_opt_in_to_onnx_without_becoming_default() -> None:
    default_policy = resolve_sbv2_runtime_policy({}, platform="win32")
    assert default_policy.runtime_profile == "windows"
    assert default_policy.allow_onnx is False
    assert default_policy.prefer_onnx is False

    opt_in_policy = resolve_sbv2_runtime_policy(
        {"SBV2_ALLOW_ONNX": "1", "SBV2_PREFER_ONNX": "1"},
        platform="win32",
    )
    assert opt_in_policy.allow_onnx is True
    assert opt_in_policy.prefer_onnx is True


def test_dummy_warmup_is_default_off_and_explicit_only() -> None:
    default_policy = resolve_sbv2_runtime_policy({}, platform="linux")
    assert default_policy.dummy_warmup_enabled is False

    enabled_policy = resolve_sbv2_runtime_policy(
        {"SBV2_DUMMY_WARMUP": "1"},
        platform="linux",
    )
    assert enabled_policy.dummy_warmup_enabled is True


def test_device_env_resolution_order() -> None:
    policy = resolve_sbv2_runtime_policy(
        {
            "TTS_DEVICE": "cpu",
            "SBV2_DEVICE": "cuda",
            "STYLE_BERT_VITS2_DEVICE": "cuda:0",
        },
        platform="linux",
    )
    assert policy.device == "cuda:0"


def test_policy_module_has_no_heavy_imports_or_side_effects() -> None:
    source = POLICY.read_text(encoding="utf-8").lower()
    forbidden = [
        "import torch",
        "import onnxruntime",
        "import style_bert",
        "subprocess",
        "requests",
        "urllib",
        "download",
        "warmup(",
        "synthesize(",
        "load_model(",
    ]
    for token in forbidden:
        assert token not in source
