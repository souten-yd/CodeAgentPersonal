import pytest

from app.asr import service


def _mock_profiles(monkeypatch, is_windows=False, is_linux=True, vendor="nvidia", runpod=False):
    class OS:
        pass

    class GPU:
        pass

    o = OS()
    o.is_windows = is_windows
    o.is_linux = is_linux
    g = GPU()
    g.vendor = vendor
    monkeypatch.setattr(service, "detect_os_profile", lambda: o)
    monkeypatch.setattr(service, "detect_gpu_profile", lambda: g)
    monkeypatch.setattr(service, "detect_runpod", lambda: runpod)


def test_default_is_faster_whisper(monkeypatch):
    monkeypatch.delenv("CODEAGENT_ASR_ENGINE", raising=False)
    _mock_profiles(monkeypatch)
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: True)
    assert service.select_asr_backend() == "faster_whisper"


def test_explicit_faster_whisper(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "faster_whisper")
    _mock_profiles(monkeypatch)
    assert service.select_asr_backend() == "faster_whisper"


def test_auto_runpod_prefers_faster(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "auto")
    _mock_profiles(monkeypatch, runpod=True)
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: True)
    assert service.select_asr_backend() == "faster_whisper"


def test_auto_windows_amd_with_assets(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "auto")
    _mock_profiles(monkeypatch, is_windows=True, is_linux=False, vendor="amd")
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: True)
    assert service.select_asr_backend() == "whisper_cpp"


def test_auto_windows_amd_without_assets(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "auto")
    _mock_profiles(monkeypatch, is_windows=True, is_linux=False, vendor="amd")
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: False)
    assert service.select_asr_backend() == "faster_whisper"


def test_explicit_whisper_cpp_missing_assets(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "whisper_cpp")
    _mock_profiles(monkeypatch, is_windows=True, is_linux=False, vendor="amd")
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: False)
    with pytest.raises(service.ASRConfigurationError):
        service.select_asr_backend()


def test_auto_linux_cuda_not_whisper_cpp(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "auto")
    _mock_profiles(monkeypatch, is_windows=False, is_linux=True, vendor="nvidia")
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: True)
    assert service.select_asr_backend() == "faster_whisper"
