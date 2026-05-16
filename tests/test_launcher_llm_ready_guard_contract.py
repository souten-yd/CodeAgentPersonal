import importlib.util
from pathlib import Path


def _load_launcher():
    path = Path("scripts/start_codeagent.py")
    spec = importlib.util.spec_from_file_location("start_codeagent_ready_guard", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _RunningProc:
    returncode = None

    def poll(self):
        return None


def test_launcher_stops_waiting_when_modelmanager_gpu_validation_failed(monkeypatch, capsys):
    launcher = _load_launcher()
    status_payload = {
        "last_model_load_status": "error",
        "gpu_validation_status": "fail",
        "cuda_init_failed": True,
        "no_usable_gpu": True,
        "gpu_validation_reason": "explicit CUDA failure",
    }
    post_calls = []
    monkeypatch.setattr(launcher, "_model_manager_status", lambda api_base: status_payload)
    monkeypatch.setattr(launcher, "request_status", lambda url: 200)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(launcher, "post_json", lambda *args, **kwargs: post_calls.append(args) or 200)

    ok = launcher.wait_llm_ready_with_model_manager(
        api_base="http://api",
        llm_base="http://llm",
        timeout_sec=180,
        cuda_expected=True,
        proc=_RunningProc(),
    )

    out = capsys.readouterr().out
    assert ok is False
    assert "[LLM][ERROR] GPU validation failed" in out
    assert "[OK] LLM ready" not in out
    assert "LLM loading... 180s" not in out
    assert post_calls == []
    assert "CodeAgent ready with warnings" in ("CodeAgent ready with warnings" if not ok else "CodeAgent ready!")


def test_launcher_warmup_only_after_gpu_validation_ok(monkeypatch, capsys):
    launcher = _load_launcher()
    statuses = [
        {"last_model_load_status": "loading", "gpu_validation_status": "pending"},
        {"last_model_load_status": "ready", "gpu_validation_status": "ok", "cuda_init_failed": False, "no_usable_gpu": False},
    ]
    monkeypatch.setattr(launcher, "_model_manager_status", lambda api_base: statuses.pop(0) if statuses else statuses[-1])
    monkeypatch.setattr(launcher, "request_status", lambda url: 200)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)

    ok = launcher.wait_llm_ready_with_model_manager(
        api_base="http://api",
        llm_base="http://llm",
        timeout_sec=4,
        cuda_expected=True,
        proc=_RunningProc(),
    )

    out = capsys.readouterr().out
    assert ok is True
    assert "gpu_validation_status=pending" in out
    assert "[OK] LLM ready" in out


def test_launcher_pending_gpu_validation_does_not_mark_ready(monkeypatch, capsys):
    launcher = _load_launcher()
    monkeypatch.setattr(launcher, "_model_manager_status", lambda api_base: {"last_model_load_status": "loading", "gpu_validation_status": "pending"})
    monkeypatch.setattr(launcher, "request_status", lambda url: 200)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)

    ok = launcher.wait_llm_ready_with_model_manager(
        api_base="http://api",
        llm_base="http://llm",
        timeout_sec=2,
        cuda_expected=True,
        proc=_RunningProc(),
    )

    out = capsys.readouterr().out
    assert ok is False
    assert "[OK] LLM ready" not in out


def test_launcher_stops_waiting_when_status_exposes_gpu_fail(monkeypatch, capsys):
    launcher = _load_launcher()
    status_payload = {
        "last_model_load_status": "error",
        "gpu_validation_status": "fail",
        "gpu_validation_reason": "cuda init failed; no usable GPU found",
        "cuda_init_failed": True,
        "no_usable_gpu": True,
    }
    sleep_calls = []

    def fake_request_json(url):
        if url == "http://api/model/status":
            return status_payload
        if url == "http://api/llm/props":
            return {}
        raise AssertionError(f"unexpected url: {url}")

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise AssertionError("wait_llm_ready_with_model_manager should not sleep after GPU fail")

    monkeypatch.setattr(launcher, "request_json", fake_request_json)
    monkeypatch.setattr(launcher, "request_status", lambda url: 200)
    monkeypatch.setattr(launcher.time, "sleep", fake_sleep)

    ok = launcher.wait_llm_ready_with_model_manager(
        api_base="http://api",
        llm_base="http://llm",
        timeout_sec=180,
        cuda_expected=True,
        proc=_RunningProc(),
    )

    out = capsys.readouterr().out
    assert ok is False
    assert sleep_calls == []
    assert "[LLM][ERROR] GPU validation failed" in out
    assert "LLM loading... 180s" not in out


def test_launcher_falls_back_to_llm_props_when_model_status_unavailable(monkeypatch, capsys):
    launcher = _load_launcher()
    sleep_calls = []

    def fake_request_json(url):
        if url == "http://api/model/status":
            return {
                "status": "unavailable",
                "current_key": "",
                "catalog": {},
                "last_model_load_status": "idle",
                "gpu_validation_status": "unavailable",
            }
        if url == "http://api/llm/props":
            return {
                "last_model_load_status": "error",
                "gpu_validation_status": "fail",
                "cuda_init_failed": True,
                "no_usable_gpu": True,
            }
        raise AssertionError(f"unexpected url: {url}")

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise AssertionError("wait_llm_ready_with_model_manager should not sleep after GPU fail")

    monkeypatch.setattr(launcher, "request_json", fake_request_json)
    monkeypatch.setattr(launcher, "request_status", lambda url: 200)
    monkeypatch.setattr(launcher.time, "sleep", fake_sleep)

    status = launcher._model_manager_status("http://api")
    assert status["gpu_validation_status"] == "fail"
    assert status["last_model_load_status"] == "error"

    ok = launcher.wait_llm_ready_with_model_manager(
        api_base="http://api",
        llm_base="http://llm",
        timeout_sec=180,
        cuda_expected=True,
        proc=_RunningProc(),
    )

    out = capsys.readouterr().out
    assert ok is False
    assert sleep_calls == []
    assert "[LLM][ERROR] GPU validation failed" in out
    assert "LLM loading... 180s" not in out
