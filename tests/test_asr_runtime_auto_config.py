from pathlib import Path

from app.asr import service
from app.asr import whisper_cpp_runtime


def _mock_profiles(monkeypatch, *, is_windows=False, is_linux=True, vendor="nvidia", runpod=False):
    monkeypatch.setattr(service, "detect_runpod", lambda: runpod)
    monkeypatch.setattr(service, "detect_os_profile", lambda: {"is_windows": is_windows, "is_linux": is_linux, "is_macos": False})
    monkeypatch.setattr(service, "detect_gpu_profile", lambda: {"vendor": vendor})


def test_effective_config_runpod_always_faster(monkeypatch):
    _mock_profiles(monkeypatch, runpod=True)
    cfg = service.resolve_effective_asr_config()
    assert cfg["effective_engine"] == "faster_whisper"
    assert cfg["effective_backend"] == "cuda"
    assert cfg["whisper_cpp_visible"] is False


def test_effective_config_windows_amd_ready(monkeypatch, tmp_path):
    _mock_profiles(monkeypatch, is_windows=True, is_linux=False, vendor="amd")
    bin_path = tmp_path / "whisper-cli.exe"
    model_path = tmp_path / "ggml-large-v3-turbo.bin"
    ffmpeg = tmp_path / "ffmpeg.exe"
    for p in (bin_path, model_path, ffmpeg):
        p.write_text("x", encoding="utf-8")
    monkeypatch.setattr(service, "resolve_whisper_cpp_binary", lambda: bin_path)
    monkeypatch.setattr(service, "resolve_whisper_cpp_model", lambda: model_path)
    monkeypatch.setattr(service, "resolve_ffmpeg_binary", lambda: ffmpeg)
    cfg = service.resolve_effective_asr_config()
    assert cfg["effective_engine"] == "whisper_cpp"
    assert cfg["effective_backend"] == "vulkan"


def test_effective_config_windows_amd_missing_ffmpeg(monkeypatch, tmp_path):
    _mock_profiles(monkeypatch, is_windows=True, is_linux=False, vendor="amd")
    bin_path = tmp_path / "whisper-cli.exe"
    model_path = tmp_path / "ggml-large-v3-turbo.bin"
    for p in (bin_path, model_path):
        p.write_text("x", encoding="utf-8")
    monkeypatch.setattr(service, "resolve_whisper_cpp_binary", lambda: bin_path)
    monkeypatch.setattr(service, "resolve_whisper_cpp_model", lambda: model_path)
    monkeypatch.setattr(service, "resolve_ffmpeg_binary", lambda: None)
    cfg = service.resolve_effective_asr_config()
    assert cfg["effective_engine"] == "faster_whisper"
    assert cfg["effective_backend"] == "cpu"
    assert cfg["warnings"]


def test_resolve_ffmpeg_binary_order(monkeypatch, tmp_path):
    env = tmp_path / "env_ffmpeg.exe"
    env.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CODEAGENT_FFMPEG_BIN", str(env))
    assert whisper_cpp_runtime.resolve_ffmpeg_binary() == env


def test_ui_hides_runpod_whisper_cpp_controls():
    ui = Path("ui.html").read_text(encoding="utf-8")
    assert "Advanced ASR override" in ui
    assert "asr_override" in ui
