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
    manager._last_ngl_search_debug = {}
    manager.last_model_load_status = "idle"
    manager.last_model_load_error = None
    manager.last_gpu_validation_status = "pending"
    manager.last_gpu_validation_reason = None
    manager.last_gpu_validation_path = None
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


def test_llama_startup_parser_accepts_offloaded_layers_line(tmp_path, monkeypatch):
    manager, _spec = _manager(tmp_path, monkeypatch)
    Path(main.LLAMA_STARTUP_LOG_PATH).write_text(
        "load_tensors: offloaded 43/43 layers to GPU\n"
        "llama_model_load: n_ctx      = 4096\n",
        encoding="utf-8",
    )

    parsed = manager._parse_llama_gpu_startup_log()

    assert parsed["n_gpu_layers"] == 43
    assert parsed["total_layers"] == 43
    assert parsed["gpu_offload_layers"] == 43
    assert parsed["offload_line"] == "load_tensors: offloaded 43/43 layers to GPU"


def test_llama_startup_parser_counts_repeating_and_output_offload(tmp_path, monkeypatch):
    manager, _spec = _manager(tmp_path, monkeypatch)
    Path(main.LLAMA_STARTUP_LOG_PATH).write_text(
        "load_tensors: offloading 41 repeating layers to GPU\n"
        "load_tensors: offloading output layer to GPU\n",
        encoding="utf-8",
    )

    parsed = manager._parse_llama_gpu_startup_log()

    assert parsed["gpu_offload_layers"] == 42
    assert "41 repeating layers" in parsed["offload_line"]
    assert "output layer" in parsed["offload_line"]


def test_llama_startup_parser_accepts_new_device_info_format(tmp_path, monkeypatch):
    manager, _spec = _manager(tmp_path, monkeypatch)
    Path(main.LLAMA_STARTUP_LOG_PATH).write_text(
        "0.00 I device_info:\n"
        "0.00 I   - CUDA0   : NVIDIA GeForce RTX 3080 (9875 MiB, 9650 MiB free)\n"
        "0.00 I system_info: n_threads = 8 | CUDA : ARCHS = 750,800,860 |\n"
        "0.31 I srv          main: model loaded\n"
        "0.31 I srv          main: server is listening on http://0.0.0.0:8080\n",
        encoding="utf-8",
    )

    parsed = manager._parse_llama_gpu_startup_log()

    assert parsed["cuda_device_detected"] is True
    assert "NVIDIA GeForce RTX 3080" in parsed["cuda_device_name"]
    assert parsed["cuda_device_free_mib"] == 9650
    assert parsed["cuda_build_detected"] is True
    assert parsed["model_loaded"] is True
    assert parsed["server_listening"] is True
    assert parsed["cuda_init_failed"] is False
    assert parsed["no_usable_gpu"] is False


def test_runpod_linux_validation_ok_without_ngl_when_cuda_and_offload_present(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {
            "n_gpu_layers": None,
            "gpu_offload_layers": 43,
            "total_layers": 43,
            "offload_line": "load_tensors: offloaded 43/43 layers to GPU",
            "cuda_buffer_mib": 2883.51,
            "cpu_buffer_mib": 2208.0,
        },
    )

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "ok"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "ok"
    assert "parsed_gpu_offload_layers=43" in manager._last_llama_gpu_log["gpu_validation_reason"]


def test_runpod_linux_validation_ok_with_cuda_buffer_and_vram_increase(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    memory_snapshots = [
        [{"index": "0", "memory_used_mib": 4, "memory_total_mib": 24576}],
        [{"index": "0", "memory_used_mib": 3956, "memory_total_mib": 24576}],
    ]
    monkeypatch.setattr(manager, "_collect_nvidia_smi_memory", lambda: memory_snapshots.pop(0))
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {"n_gpu_layers": None, "cuda_buffer_mib": 2883.51, "cpu_buffer_mib": 2208.0},
    )

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "ok"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "ok"
    assert "nvidia_smi_memory_delta_mib=3952" in manager._last_llama_gpu_log["gpu_validation_reason"]


def test_runpod_linux_validation_accepts_new_llama_device_info_format(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {
            "n_gpu_layers": None,
            "gpu_offload_layers": None,
            "cuda_buffer_mib": None,
            "cuda_device_detected": True,
            "cuda_device_name": "NVIDIA GeForce RTX 3080",
            "cuda_device_free_mib": 9650,
            "cuda_build_detected": True,
            "model_loaded": True,
            "server_listening": True,
            "cuda_init_failed": False,
            "no_usable_gpu": False,
        },
    )
    monkeypatch.setattr(
        manager,
        "_probe_llama_cuda_runtime_preflight",
        lambda: (_ for _ in ()).throw(
            AssertionError("CUDA preflight should not run before new llama device_info acceptance")
        ),
    )

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "ok"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "ok"
    assert "accepted_new_llama_device_info_format" in manager._last_llama_gpu_log["gpu_validation_reason"]


def test_runpod_linux_validation_rejects_no_usable_gpu_even_with_server_lines(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {
            "cuda_device_detected": False,
            "cuda_build_detected": True,
            "model_loaded": True,
            "server_listening": True,
            "cuda_init_failed": True,
            "no_usable_gpu": True,
        },
    )

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "fail"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "fail"
    reason = manager._last_llama_gpu_log["gpu_validation_reason"]
    assert "no usable GPU" in reason or "cuda init failed" in reason


def test_cuda_debug_fixture_with_offloaded_layers_is_not_failed(tmp_path, monkeypatch):
    manager, _spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._last_nvidia_smi_before = [{"index": "0", "memory_used_mib": 4, "memory_total_mib": 24576}]
    manager._last_nvidia_smi_after = [{"index": "0", "memory_used_mib": 3956, "memory_total_mib": 24576}]
    manager._last_llama_gpu_log = {
        "requested_ngl": 999,
        "n_gpu_layers": 43,
        "gpu_offload_layers": 43,
        "total_layers": 43,
        "offload_line": "load_tensors: offloaded 43/43 layers to GPU",
        "cuda_buffer_mib": 2883.51,
        "cpu_buffer_mib": 2208.0,
    }
    manager._record_ngl_search_debug(
        requested_ngl_initial=999,
        search_attempts=[{"ngl": 999, "result": "ok", "binary": False}],
        final_requested_ngl=999,
        final_parsed_n_gpu_layers=43,
    )
    Path(main.LLAMA_STARTUP_LOG_PATH).write_text("load_tensors: offloaded 43/43 layers to GPU\n", encoding="utf-8")

    debug = manager.cuda_debug_dict()

    assert debug["gpu_validation_status"] == "ok"
    assert debug["parsed_gpu_offload_layers"] == 43
    assert debug["parsed_total_layers"] == 43
    assert debug["final_requested_ngl"] == 999
    assert debug["final_parsed_n_gpu_layers"] == 43
    assert debug["search_attempts"][0]["result"] == "ok"
    assert "offloaded 43/43" in debug["llama_startup_log_tail"]


def test_runpod_linux_validation_fails_for_cpu_only_no_cuda_no_vram_increase(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    memory_snapshots = [
        [{"index": "0", "memory_used_mib": 4, "memory_total_mib": 24576}],
        [{"index": "0", "memory_used_mib": 4, "memory_total_mib": 24576}],
    ]
    monkeypatch.setattr(manager, "_collect_nvidia_smi_memory", lambda: memory_snapshots.pop(0))
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {"n_gpu_layers": None, "cuda_buffer_mib": None, "cpu_buffer_mib": 2208.0},
    )

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "fail"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "fail"
    assert "CUDA buffer not detected" in manager._last_llama_gpu_log["gpu_validation_reason"]

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


def test_runpod_linux_high_oom_half_ok_then_binary_search_saves_max_success(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    spec["proven_ngl"] = 0
    spec["gpu_layers"] = 0
    runtime = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._last_runtime_decision = runtime
    calls = []
    saved = []

    monkeypatch.setattr(manager, "_predict_ngl_with_kv", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_load_ngl_ctx_profiles", lambda _spec: {})
    monkeypatch.setattr(manager, "_ngl_from_profiles", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_save_proven_ngl", lambda _spec, ngl: saved.append(("proven", ngl)))
    monkeypatch.setattr(manager, "_save_ngl_ctx_profile", lambda _spec, ctx, ngl: saved.append(("ctx", ctx, ngl)))
    monkeypatch.setattr(main, "_read_gguf_metadata", lambda path: {})

    def fake_try(_spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit):
        calls.append(gpu_layers)
        if gpu_layers <= 624:
            manager._last_llama_gpu_log = {"n_gpu_layers": gpu_layers, "cuda_buffer_mib": 100.0, "cpu_buffer_mib": 10.0}
            return "ok"
        return "oom"

    monkeypatch.setattr(manager, "_try_start_once", fake_try)

    assert manager._start_linux(spec, "q8_0", "q8_0", "nvidia", lambda *a: None, 999, 0, runtime) is True

    assert calls[:4] == [999, 499, 749, 624]
    assert calls[-1] == 624
    assert 624 in calls
    assert 499 != calls[-1]
    assert saved[-2:] == [("proven", 624), ("ctx", 4096, 624)]
    assert manager.cuda_debug_dict()["final_requested_ngl"] == 624


def test_runpod_linux_saves_parsed_ngl_when_requested_differs(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    spec["proven_ngl"] = 0
    spec["gpu_layers"] = 0
    runtime = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._last_runtime_decision = runtime
    saved = []

    monkeypatch.setattr(manager, "_predict_ngl_with_kv", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_load_ngl_ctx_profiles", lambda _spec: {})
    monkeypatch.setattr(manager, "_ngl_from_profiles", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_save_proven_ngl", lambda _spec, ngl: saved.append(("proven", ngl)))
    monkeypatch.setattr(manager, "_save_ngl_ctx_profile", lambda _spec, ctx, ngl: saved.append(("ctx", ctx, ngl)))
    monkeypatch.setattr(main, "_read_gguf_metadata", lambda path: {})

    def fake_try(_spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit):
        manager._last_llama_gpu_log = {"n_gpu_layers": 60, "cuda_buffer_mib": 100.0, "cpu_buffer_mib": 10.0}
        return "ok"

    monkeypatch.setattr(manager, "_try_start_once", fake_try)

    assert manager._start_linux(spec, "q8_0", "q8_0", "nvidia", lambda *a: None, 999, 0, runtime) is True
    assert saved[-2:] == [("proven", 60), ("ctx", 4096, 60)]
    assert manager.cuda_debug_dict()["final_requested_ngl"] == 999
    assert manager.cuda_debug_dict()["final_parsed_n_gpu_layers"] == 60


def test_runpod_linux_uses_calc_gpu_layers_when_row_ngl_missing(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    spec["proven_ngl"] = 0
    spec["gpu_layers"] = 0
    runtime = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._last_runtime_decision = runtime
    calls = []

    monkeypatch.setattr(manager, "_predict_ngl_with_kv", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_load_ngl_ctx_profiles", lambda _spec: {})
    monkeypatch.setattr(manager, "_ngl_from_profiles", lambda *args, **kwargs: -1)
    monkeypatch.setattr(manager, "_save_proven_ngl", lambda _spec, ngl: None)
    monkeypatch.setattr(manager, "_save_ngl_ctx_profile", lambda _spec, ctx, ngl: None)
    monkeypatch.setattr(main, "_read_gguf_metadata", lambda path: {})

    def fake_try(_spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit):
        calls.append(gpu_layers)
        manager._last_llama_gpu_log = {"n_gpu_layers": gpu_layers, "cuda_buffer_mib": 100.0, "cpu_buffer_mib": 10.0}
        return "ok"

    monkeypatch.setattr(manager, "_try_start_once", fake_try)

    assert manager._start_linux(spec, "q8_0", "q8_0", "nvidia", lambda *a: None, 123, 0, runtime) is True
    assert calls == [123]


def test_runpod_linux_sets_parser_stale_warning_when_new_format_has_no_legacy_fields(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {
            "cuda_device_detected": True,
            "cuda_build_detected": True,
            "model_loaded": True,
            "server_listening": True,
            "n_gpu_layers": None,
            "gpu_offload_layers": None,
            "cuda_buffer_mib": None,
            "cuda_init_failed": False,
            "no_usable_gpu": False,
        },
    )

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "ok"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "ok"
    assert manager._last_llama_gpu_log["gpu_validation_path"] == "new_llama_device_info"
    assert manager._last_llama_gpu_log["llama_log_parser_stale_suspected"] is True
    assert any("parser may be stale" in hint for hint in manager._last_startup_hints)


def test_runpod_linux_parser_independent_readiness_accepts_health_process_cuda_without_legacy_log(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {
            "n_gpu_layers": None,
            "gpu_offload_layers": None,
            "cuda_buffer_mib": None,
            "cuda_device_detected": False,
            "cuda_build_detected": False,
            "model_loaded": False,
            "server_listening": False,
            "cuda_init_failed": False,
            "no_usable_gpu": False,
        },
    )
    monkeypatch.setattr(manager, "_probe_llama_cuda_runtime_preflight", lambda: {"cuInit_rc": 0, "torch_cuda_available": True})

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "ok"
    assert manager._last_llama_gpu_log["gpu_validation_path"] == "parser_independent_readiness"


def test_runpod_linux_parser_independent_readiness_rejects_cuda_init_failed(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(
        manager,
        "_parse_llama_gpu_startup_log",
        lambda: {"cuda_init_failed": True, "no_usable_gpu": False, "n_gpu_layers": None, "gpu_offload_layers": None, "cuda_buffer_mib": None},
    )
    monkeypatch.setattr(manager, "_probe_llama_cuda_runtime_preflight", lambda: {"cuInit_rc": 0, "torch_cuda_available": True})

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "fail"
    assert manager._last_llama_gpu_log["gpu_validation_status"] == "fail"


def test_runpod_linux_parser_independent_readiness_rejects_process_exit(tmp_path, monkeypatch):
    class _ExitedPopen(_FakePopen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.returncode = 1

        def poll(self):
            return 1

    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    monkeypatch.setattr(main, "IS_RUNPOD_RUNTIME", True)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _ExitedPopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(manager, "_probe_llama_cuda_runtime_preflight", lambda: {"cuInit_rc": 0, "torch_cuda_available": True})

    result = manager._try_start_once(spec, gpu_layers=999, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="nvidia", emit=lambda *a: None)

    assert result == "fail"


def test_cuda_debug_payload_contains_parser_stale_fields(tmp_path, monkeypatch):
    manager, _spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._process = _FakePopen(["llama"])
    manager._last_llama_gpu_log = {
        "cuda_device_detected": True,
        "cuda_build_detected": True,
        "model_loaded": True,
        "server_listening": True,
        "n_gpu_layers": None,
        "gpu_offload_layers": None,
        "cuda_buffer_mib": None,
        "cuda_init_failed": False,
        "no_usable_gpu": False,
        "llama_readiness_signals": {"http_signal": {"health_ok": True}, "process_signal": {"alive": True}},
    }

    debug = manager.cuda_debug_dict()

    assert debug["llama_log_parser_stale_suspected"] is True
    assert debug["llama_log_parser_stale_reason"]
    assert debug["gpu_validation_path"] == "new_llama_device_info"
    assert "http_signal" in debug["llama_readiness_signals"]


def test_windows_amd_parser_independent_readiness_does_not_require_cuda(tmp_path, monkeypatch):
    captured = {}
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": False,
        "is_linux": False,
        "is_windows": True,
        "intended_backend": "vulkan",
        "gpu_vendor": "amd",
        "os_profile": {"os_name": "nt", "is_windows": True},
    }
    monkeypatch.setattr(main._sp, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: captured.setdefault("cmd", cmd) or _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(manager, "_parse_llama_gpu_startup_log", lambda: {"n_gpu_layers": None, "gpu_offload_layers": None, "cuda_buffer_mib": None})
    monkeypatch.setattr(manager, "_collect_nvidia_smi_memory", lambda: [])
    validate = mock.Mock(side_effect=AssertionError("Runpod validation must not run for Windows AMD"))
    monkeypatch.setattr(manager, "_validate_runpod_linux_gpu_startup", validate)

    with mock.patch.object(main.os, "name", "nt"):
        result = manager._try_start_once(spec, gpu_layers=None, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="amd", emit=lambda *a: None)

    assert result == "ok"
    validate.assert_not_called()
    assert not any("CUDA buffer not detected" in hint or "parser may be stale" in hint for hint in manager._last_startup_hints)


def test_windows_amd_does_not_run_cuinit_preflight(tmp_path, monkeypatch):
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": False,
        "is_linux": False,
        "is_windows": True,
        "intended_backend": "vulkan",
        "gpu_vendor": "amd",
        "os_profile": {"os_name": "nt", "is_windows": True},
    }
    monkeypatch.setattr(main._sp, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: _FakePopen(cmd, stdout, stderr, creationflags))
    monkeypatch.setattr(manager, "_parse_llama_gpu_startup_log", lambda: {"n_gpu_layers": None, "gpu_offload_layers": None, "cuda_buffer_mib": None})
    monkeypatch.setattr(manager, "_probe_llama_cuda_runtime_preflight", lambda: (_ for _ in ()).throw(RuntimeError("cuInit should not run")))

    with mock.patch.object(main.os, "name", "nt"):
        result = manager._try_start_once(spec, gpu_layers=None, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="amd", emit=lambda *a: None)

    assert result == "ok"


def test_windows_amd_keeps_ngl_omitted(tmp_path, monkeypatch):
    captured = {}
    manager, spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": False,
        "is_linux": False,
        "is_windows": True,
        "intended_backend": "vulkan",
        "gpu_vendor": "amd",
        "os_profile": {"os_name": "nt", "is_windows": True},
    }
    monkeypatch.setattr(main._sp, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(main._sp, "Popen", lambda cmd, stdout=None, stderr=None, creationflags=0: captured.setdefault("cmd", cmd) or _FakePopen(cmd, stdout, stderr, creationflags))

    with mock.patch.object(main.os, "name", "nt"):
        result = manager._try_start_once(spec, gpu_layers=None, eff_ck="q8_0", eff_cv="q8_0", gpu_vendor="amd", emit=lambda *a: None)

    assert result == "ok"
    assert "-ngl" not in captured["cmd"]
    assert "--n-gpu-layers" not in captured["cmd"]
    assert "--flash-attn" not in captured["cmd"]
    assert "on" not in captured["cmd"]


def test_gpu_validation_failed_is_not_parser_stale_success(tmp_path, monkeypatch):
    manager, _spec = _manager(tmp_path, monkeypatch)
    manager._last_runtime_decision = {
        "runpod_detected": True,
        "is_linux": True,
        "is_windows": False,
        "intended_backend": "cuda",
        "gpu_vendor": "nvidia",
        "os_profile": {"os_name": "posix", "is_linux": True},
    }
    manager._process = _FakePopen(["llama"])
    parsed = {
        "model_loaded": True,
        "server_listening": True,
        "cuda_init_failed": True,
        "no_usable_gpu": True,
        "cuda_device_detected": True,
        "cuda_build_detected": True,
        "n_gpu_layers": None,
        "gpu_offload_layers": None,
        "cuda_buffer_mib": None,
        "llama_readiness_signals": {"http_signal": {"health_ok": True}, "process_signal": {"alive": True}},
    }

    ok, status, reason = manager._validate_runpod_linux_gpu_startup(parsed)

    assert ok is False
    assert status == "fail"
    assert "cuda init failed" in reason
    assert parsed["gpu_validation_path"] == "explicit_cuda_failure"
    assert parsed["llama_log_parser_stale_suspected"] is False
