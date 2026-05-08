from pathlib import Path
from unittest import mock

import requests

import main


class _FakeResponse:
    status_code = 200


class _FakePopen:
    def __init__(self, cmd, stdout=None, stderr=None, creationflags=0):
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr
        self.creationflags = creationflags
        self.pid = 12345
        self.returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.returncode = -9


def _manager(tmp_path, monkeypatch):
    llama = tmp_path / "llama-server"
    model = tmp_path / "model.gguf"
    llama.write_text("#!/bin/sh\n", encoding="utf-8")
    model.write_text("fake", encoding="utf-8")

    manager = main.ModelManager.__new__(main.ModelManager)
    manager.llama_path = str(llama)
    manager.llm_port = 18080
    manager._process = None
    manager._status = "ready"
    manager._switch_eta = 9999999999
    manager._last_start_cmd = ""
    manager._last_startup_hints = []
    manager._last_llama_gpu_log = {}
    manager._last_runtime_decision = {}
    manager._last_nvidia_smi_before = []
    manager._last_nvidia_smi_after = []
    manager._startup_log_fd = None

    monkeypatch.setattr(manager, "_collect_nvidia_smi_memory", lambda: [])
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _FakeResponse())
    monkeypatch.setattr(main, "LLAMA_STARTUP_LOG_PATH", str(tmp_path / "llama_startup.log"))

    spec = {
        "name": "Test GGUF",
        "path": str(model),
        "ctx": 4096,
        "threads": 4,
        "load_sec": 60,
        "gpu_layers": 37,
        "proven_ngl": 55,
        "extra_args": [],
    }
    return manager, spec


def test_runpod_linux_try_start_requires_explicit_ngl_in_full_cmd(tmp_path, monkeypatch):
    captured = {}

    def fake_popen(cmd, stdout=None, stderr=None, creationflags=0):
        captured["cmd"] = cmd
        return _FakePopen(cmd, stdout=stdout, stderr=stderr, creationflags=creationflags)

    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    assert main.os.name != "nt"
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", fake_popen)
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {"n_gpu_layers": 55, "cuda_buffer_mib": 123.0, "cpu_buffer_mib": 45.0},
    )

    result = manager._try_start_once(spec, gpu_layers=55, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "ok"
    assert captured["cmd"][captured["cmd"].index("-ngl") + 1] == "55"
    assert "-ngl 55" in manager._last_start_cmd


def test_runpod_linux_try_start_rejects_autofit_without_ngl(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    assert main.os.name != "nt"
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)

    result = manager._try_start_once(spec, gpu_layers=None, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "fail"
    assert "-ngl" not in manager._last_start_cmd
    assert any("requires explicit -ngl" in hint for hint in manager._last_startup_hints)


def test_windows_try_start_allows_autofit_ngl_omission(tmp_path, monkeypatch):
    captured = {}

    def fake_popen(cmd, stdout=None, stderr=None, creationflags=0):
        captured["cmd"] = cmd
        return _FakePopen(cmd, stdout=stdout, stderr=stderr, creationflags=creationflags)

    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": False,
        "is_linux": False,
        "is_windows": True,
        "intended_backend": "vulkan",
        "os_profile": {"os_name": "nt", "is_windows": True},
    }
    monkeypatch.setattr(main._sp, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(main._sp, "Popen", fake_popen)
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {"n_gpu_layers": None, "cuda_buffer_mib": None, "cpu_buffer_mib": None},
    )

    with mock.patch.object(main.os, "name", "nt"):
        result = manager._try_start_once(spec, gpu_layers=None, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="amd", emit=lambda *a: None)

    assert result == "ok"
    assert "-ngl" not in captured["cmd"]
    assert "--n-gpu-layers" not in captured["cmd"]
    assert "-ngl=auto(fit)" in Path(main.LLAMA_STARTUP_LOG_PATH).read_text(encoding="utf-8", errors="ignore")


def test_runpod_linux_start_uses_proven_ngl_before_gpu_layers(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    calls = []
    runtime = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._last_runtime_decision = runtime
    monkeypatch.setattr(manager, "_predict_ngl_with_kv", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_load_ngl_ctx_profiles", lambda _spec: {})
    monkeypatch.setattr(manager, "_ngl_from_profiles", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_save_proven_ngl", lambda _spec, ngl: None)
    monkeypatch.setattr(manager, "_save_ngl_ctx_profile", lambda _spec, ctx, ngl: None)
    monkeypatch.setattr(main, "_read_gguf_metadata", lambda path: {})

    def fake_try(_spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit):
        calls.append(gpu_layers)
        return "ok"

    monkeypatch.setattr(manager, "_try_start_once", fake_try)

    assert manager._start_linux(spec, "q8_0", "q8_0", "nvidia", lambda *a: None, 999, 55, runtime) is True
    assert calls == [55]


def test_runpod_linux_start_falls_back_to_999_without_row_ngl(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    spec["proven_ngl"] = 0
    spec["gpu_layers"] = 0
    calls = []
    runtime = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._last_runtime_decision = runtime
    monkeypatch.setattr(manager, "_predict_ngl_with_kv", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_load_ngl_ctx_profiles", lambda _spec: {})
    monkeypatch.setattr(manager, "_ngl_from_profiles", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_save_proven_ngl", lambda _spec, ngl: None)
    monkeypatch.setattr(manager, "_save_ngl_ctx_profile", lambda _spec, ctx, ngl: None)
    monkeypatch.setattr(main, "_read_gguf_metadata", lambda path: {})

    def fake_try(_spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit):
        calls.append(gpu_layers)
        return "ok"

    monkeypatch.setattr(manager, "_try_start_once", fake_try)

    assert manager._start_linux(spec, "q8_0", "q8_0", "nvidia", lambda *a: None, 999, 0, runtime) is True
    assert calls == [999]
