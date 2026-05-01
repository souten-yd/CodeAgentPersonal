import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from app.tts import style_bert_vits2_runtime as runtime


def test_worker_env_sets_jit_and_no_user_site_and_unsets_pythonhome(monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "/tmp/pyhome")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(runtime, "_venv_dir", lambda: "/opt/sbv2/.venv")

    env = runtime._worker_env()

    assert env["PYTORCH_JIT"] == "0"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert "PYTHONHOME" not in env
    assert env["VIRTUAL_ENV"] == "/opt/sbv2/.venv"
    assert env["PATH"].startswith("/opt/sbv2/.venv/bin")


def test_pick_device_runpod_linux_keeps_cuda(monkeypatch):
    monkeypatch.setattr(runtime.os, "name", "posix", raising=False)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    assert runtime._pick_device({"device": "cuda"}) == "cuda"


def test_pick_device_windows_fallback_to_cpu(monkeypatch):
    monkeypatch.setattr(runtime.os, "name", "nt", raising=False)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    assert runtime._pick_device({"device": "cuda"}) == "cpu"


def test_likely_reason_deberta_jit_segfault_detected():
    stderr_tail = "... transformers.models.deberta_v2.modeling_deberta_v2 ... torch.jit.script ... Segmentation fault"
    reason = runtime.StyleBertVITS2Runtime._likely_reason_from_worker_error(139, stderr_tail)
    assert reason == "deberta_v2_torch_jit_segfault"


def test_worker_popen_env_includes_required_settings(monkeypatch, tmp_path):
    script_py = tmp_path / "python"
    script_py.write_text("#!/bin/sh\n", encoding="utf-8")
    script_py.chmod(0o755)
    monkeypatch.setattr(runtime, "_python_path", lambda: str(script_py))
    monkeypatch.setattr(runtime, "_worker_env", lambda: {"PYTORCH_JIT": "0", "PYTHONNOUSERSITE": "1", "PATH": "/x"})

    captured = {}

    class DummyProc:
        def __init__(self):
            self.stderr = None

        def poll(self):
            return None

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        return DummyProc()

    monkeypatch.setattr(runtime.subprocess, "Popen", fake_popen)
    rt = runtime.StyleBertVITS2Runtime()
    rt._ensure_worker_started()
    assert captured["env"]["PYTORCH_JIT"] == "0"
    assert captured["env"]["PYTHONNOUSERSITE"] == "1"
