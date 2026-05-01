import pytest

from app.asr import service


def _mock_profiles(monkeypatch, is_windows=False, is_linux=True, vendor="nvidia", runpod=False):
    os_profile = {
        "is_windows": is_windows,
        "is_linux": is_linux,
        "is_macos": False,
    }
    gpu_profile = {
        "vendor": vendor,
    }
    monkeypatch.setattr(service, "detect_os_profile", lambda: os_profile)
    monkeypatch.setattr(service, "detect_gpu_profile", lambda: gpu_profile)
    monkeypatch.setattr(service, "detect_runpod", lambda: runpod)


def test_auto_with_dict_profiles_no_attribute_error(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "auto")
    _mock_profiles(monkeypatch, is_windows=False, is_linux=True, vendor="nvidia")
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: True)
    assert service.select_asr_backend() == "faster_whisper"


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


def test_auto_runpod_skips_profile_detection(monkeypatch):
    monkeypatch.setenv("CODEAGENT_ASR_ENGINE", "auto")
    monkeypatch.setattr(service, "detect_runpod", lambda: True)

    def _should_not_be_called():
        raise AssertionError("profile detection should not be called on runpod")

    monkeypatch.setattr(service, "detect_os_profile", _should_not_be_called)
    monkeypatch.setattr(service, "detect_gpu_profile", _should_not_be_called)
    monkeypatch.setattr(service, "whisper_cpp_ready", lambda: True)
    assert service.select_asr_backend() == "faster_whisper"
