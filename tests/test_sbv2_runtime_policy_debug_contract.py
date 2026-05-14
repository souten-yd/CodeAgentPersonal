from pathlib import Path

from app.services.audio_runtime import build_sbv2_runtime_policy_debug


def test_sbv2_runtime_policy_debug_has_safe_fields():
    data = build_sbv2_runtime_policy_debug({}, platform="linux")
    assert data["engine"] == "style_bert_vits2"
    assert data["default_model"] == "koharune-ami"
    assert data["prefer_safetensors"] is True
    assert data["allow_onnx"] is False
    assert data["prefer_onnx"] is False
    assert data["force_pytorch_jit_zero"] is False
    assert data["dummy_warmup_enabled"] is False
    assert data["import_time_side_effects_allowed"] is False


def test_sbv2_runtime_policy_debug_runpod_is_safe():
    data = build_sbv2_runtime_policy_debug(
        {
            "RUNPOD_POD_ID": "pod",
            "SBV2_ALLOW_ONNX": "1",
            "SBV2_PREFER_ONNX": "1",
            "PYTORCH_JIT": "0",
        },
        platform="linux",
    )
    assert data["runtime_profile"] == "runpod"
    assert data["allow_onnx"] is False
    assert data["prefer_onnx"] is False
    assert data["force_pytorch_jit_zero"] is False


def test_sbv2_runtime_policy_debug_windows_onnx_opt_in():
    data = build_sbv2_runtime_policy_debug(
        {
            "SBV2_ALLOW_ONNX": "1",
            "SBV2_PREFER_ONNX": "1",
        },
        platform="win32",
    )
    assert data["runtime_profile"] == "windows"
    assert data["allow_onnx"] is True
    assert data["prefer_onnx"] is True


ROOT = Path(__file__).resolve().parents[1]
AUDIO_RUNTIME = ROOT / "app" / "services" / "audio_runtime.py"


def test_audio_runtime_policy_debug_has_no_heavy_runtime_side_effects():
    source = AUDIO_RUNTIME.read_text(encoding="utf-8").lower()
    marker = "build_sbv2_runtime_policy_debug"
    assert marker in source
    start = source.index(marker)
    body = source[start : start + 2500]
    forbidden = [
        "import torch",
        "import onnxruntime",
        "style_bert",
        "subprocess",
        "download",
        "warmup(",
        "synthesize(",
        "load_model(",
    ]
    for token in forbidden:
        assert token not in body


def test_sbv2_runtime_policy_debug_defaults_to_current_platform(monkeypatch):
    import sys

    data = build_sbv2_runtime_policy_debug({}, platform=None)
    if sys.platform.startswith("win"):
        assert data["runtime_profile"] == "windows"
    elif "linux" in sys.platform:
        assert data["runtime_profile"] in {"generic", "linux_nvidia"}


def test_audio_runtime_policy_resolution_passes_sys_platform():
    source = AUDIO_RUNTIME.read_text(encoding="utf-8")
    assert "import sys" in source
    assert "platform=platform or sys.platform" in source
    assert "platform=sys.platform" in source
