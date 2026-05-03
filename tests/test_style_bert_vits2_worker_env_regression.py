import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from app.tts import style_bert_vits2_runtime as runtime


def test_worker_env_windows_sets_jit_and_no_user_site_and_unsets_pythonhome(monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "/tmp/pyhome")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(runtime, "_venv_dir", lambda: "/opt/sbv2/.venv")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")

    env = runtime._worker_env()

    assert env["PYTORCH_JIT"] == "0"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert "PYTHONHOME" not in env
    assert env["VIRTUAL_ENV"] == "/opt/sbv2/.venv"
    assert env["PATH"].startswith("/opt/sbv2/.venv/bin")


def test_worker_env_runpod_linux_does_not_set_jit_by_default(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.delenv("PYTORCH_JIT", raising=False)
    monkeypatch.delenv("CODEAGENT_STYLE_BERT_VITS2_DISABLE_PYTORCH_JIT", raising=False)
    monkeypatch.setattr(runtime, "_venv_dir", lambda: "/opt/sbv2/.venv")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    env = runtime._worker_env()
    assert "PYTORCH_JIT" not in env


def test_worker_env_disable_jit_override(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("CODEAGENT_STYLE_BERT_VITS2_DISABLE_PYTORCH_JIT", "1")
    monkeypatch.setattr(runtime, "_venv_dir", lambda: "/opt/sbv2/.venv")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    env = runtime._worker_env()
    assert env["PYTORCH_JIT"] == "0"


def test_worker_env_enable_jit_override_removes_var(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("PYTORCH_JIT", "0")
    monkeypatch.setenv("CODEAGENT_STYLE_BERT_VITS2_DISABLE_PYTORCH_JIT", "0")
    monkeypatch.setattr(runtime, "_venv_dir", lambda: "/opt/sbv2/.venv")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    env = runtime._worker_env()
    assert "PYTORCH_JIT" not in env


def test_onnx_internal_warmup_default_windows_false(monkeypatch):
    monkeypatch.delenv("CODEAGENT_STYLE_BERT_VITS2_ONNX_INTERNAL_WARMUP", raising=False)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    assert runtime._onnx_internal_warmup_enabled() is False


def test_onnx_internal_warmup_default_linux_false(monkeypatch):
    monkeypatch.delenv("CODEAGENT_STYLE_BERT_VITS2_ONNX_INTERNAL_WARMUP", raising=False)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    assert runtime._onnx_internal_warmup_enabled() is False


def test_onnx_internal_warmup_env_override_true_windows(monkeypatch):
    monkeypatch.setenv("CODEAGENT_STYLE_BERT_VITS2_ONNX_INTERNAL_WARMUP", "1")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    assert runtime._onnx_internal_warmup_enabled() is True


def test_onnx_internal_warmup_env_override_true_linux(monkeypatch):
    monkeypatch.setenv("CODEAGENT_STYLE_BERT_VITS2_ONNX_INTERNAL_WARMUP", "1")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    assert runtime._onnx_internal_warmup_enabled() is True


def test_pick_device_runpod_linux_keeps_cuda(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    assert runtime._pick_device({"device": "cuda"}) == "cuda"


def test_pick_device_windows_fallback_to_cpu(monkeypatch):
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
