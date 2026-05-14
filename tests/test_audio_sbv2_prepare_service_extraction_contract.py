from pathlib import Path
from types import SimpleNamespace

import main
from app.services import audio_runtime


SERVICE = Path("app/services/audio_runtime.py")
MAIN = Path("main.py")


def _single_http_route(path: str, method: str):
    routes = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1, f"expected one {method} {path}, got {len(routes)}"
    return routes[0]


def _single_websocket_route(path: str):
    routes = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path and not hasattr(route, "methods")
    ]
    assert len(routes) == 1, f"expected one websocket {path}, got {len(routes)}"
    return routes[0]


def _base_status():
    return {
        "repo_exists": True,
        "venv_exists": True,
        "python_exists": True,
        "python_executable": True,
        "site_packages_exists": True,
        "init_flag_exists": True,
    }


def _deps(*, status=None, runtime_results=None, model_checks=None):
    runtime_results = runtime_results if runtime_results is not None else []
    model_checks = model_checks if model_checks is not None else []
    status = dict(status or _base_status())

    def runtime_prepare(payload):
        runtime_results.append(dict(payload))
        return {"status": "ready", "device": "cuda", "warmup_elapsed_ms": 12, "cache_hit": False}

    return audio_runtime.Sbv2PrepareServiceDependencies(
        logger=SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        prepare_id_factory=lambda: "prepare-fixed",
        default_model=lambda: "koharune-ami",
        repo_dir="/tmp/sbv2/repo",
        venv_dir="/tmp/sbv2/venv",
        models_dir="/tmp/sbv2/models",
        init_flag="/tmp/sbv2/.initialized",
        legacy_models_dir="/tmp/sbv2/legacy_models",
        models_dir_env="STYLE_BERT_VITS2_MODELS_DIR",
        upstream_models_dir_envs=("SBV2_MODELS_DIR",),
        python_path=lambda: "/tmp/sbv2/venv/bin/python",
        site_packages_dir=lambda: "/tmp/sbv2/venv/site-packages",
        validate_prerequisites=lambda: (True, ""),
        ensure_pth_file=lambda: (True, ""),
        prepare_status=lambda: dict(status),
        models_ready=lambda: (True, ["koharune-ami"], ""),
        runtime_importable=lambda: (True, ""),
        run_initialize=lambda *a, **k: SimpleNamespace(stdout="", stderr=""),
        log_model_locations=lambda _prepare_id, _stage: None,
        migrate_legacy_models_if_needed=lambda _prepare_id: (False, []),
        is_valid_model_dir_name=lambda model: model == "koharune-ami",
        ensure_model_exists=lambda model, models_dir: model_checks.append((model, models_dir)),
        runtime_prepare=runtime_prepare,
        style_error_factory=lambda **kwargs: RuntimeError(kwargs),
    )


def test_sbv2_prepare_service_symbols_exist_and_audio_runtime_stays_route_neutral():
    assert hasattr(audio_runtime, "Sbv2PrepareServiceDependencies")
    assert hasattr(audio_runtime, "run_sbv2_prepare_service_body")
    assert callable(audio_runtime.run_sbv2_prepare_service_body)

    text = SERVICE.read_text(encoding="utf-8")
    for forbidden in ["import main", "from main import", "APIRouter", "@router", "@app"]:
        assert forbidden not in text

    top_level_imports = "\n".join(
        line for line in text.splitlines() if line.startswith(("import ", "from "))
    )
    for forbidden in [
        "import torch",
        "from torch",
        "import ctranslate2",
        "from ctranslate2",
        "import faster_whisper",
        "from faster_whisper",
        "style_bert_vits2_runtime",
        "StyleBertVITS2Runtime",
    ]:
        assert forbidden not in top_level_imports

    assert "detect_audio_runtime()" not in text


def test_sbv2_prepare_and_high_risk_audio_route_owners_remain_main():
    expected_main_routes = [
        ("/api/tts/style-bert-vits2/prepare", "POST", "api_style_bert_vits2_prepare"),
        ("/tts/synthesize", "POST", "tts_synthesize_api"),
        ("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api"),
        ("/voice/transcribe", "POST", "voice_transcribe_api"),
    ]
    for path, method, handler_name in expected_main_routes:
        route = _single_http_route(path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name

    route = _single_websocket_route("/echo/stream")
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "echo_stream_ws"

    main_text = MAIN.read_text(encoding="utf-8")
    assert '@app.post("/api/tts/style-bert-vits2/prepare")' in main_text
    assert "run_sbv2_prepare_service_body" in main_text
    assert "Sbv2PrepareServiceDependencies" in main_text


def test_sbv2_prepare_service_body_uses_dependency_injection_and_preserves_success_shape():
    runtime_results = []
    model_checks = []
    result = audio_runtime.run_sbv2_prepare_service_body(
        {"model": "koharune-ami", "device": "CUDA"},
        _deps(runtime_results=runtime_results, model_checks=model_checks),
    )

    assert isinstance(result, audio_runtime.Sbv2PrepareServiceResponse)
    assert result.status_code == 200
    payload = result.content
    assert payload["prepare_id"] == "prepare-fixed"
    assert payload["models"] == ["koharune-ami"]
    assert payload["models_ready"] is True
    assert payload["initialized_now"] is False
    assert payload["initialize_action"] == "already_initialized"
    assert payload["setup_ready"] is True
    assert payload["ready"] is True
    assert payload["runtime_ready"] is True
    assert payload["runtime_prepare"]["device"] == "cuda"
    assert payload["runtime_prepare"]["warmup_elapsed_ms"] == 12
    assert payload["runtime_prepare"]["cache_hit"] is False
    assert runtime_results == [{"model": "koharune-ami", "device": "cuda"}]
    assert model_checks == [("koharune-ami", "/tmp/sbv2/models")]
    policy = payload["sbv2_runtime_policy"]
    assert policy["engine"] == "style_bert_vits2"
    assert policy["default_model"] == "koharune-ami"
    assert policy["prefer_safetensors"] is True
    assert policy["allow_onnx"] is False
    assert policy["prefer_onnx"] is False
    assert policy["force_pytorch_jit_zero"] is False
    assert policy["dummy_warmup_enabled"] is False
    assert policy["import_time_side_effects_allowed"] is False


def test_sbv2_prepare_service_body_preserves_degraded_503_payload_shape():
    deps = _deps()
    deps = audio_runtime.Sbv2PrepareServiceDependencies(
        **{**deps.__dict__, "validate_prerequisites": lambda: (False, "missing runtime")}
    )

    result = audio_runtime.run_sbv2_prepare_service_body({"model": "koharune-ami"}, deps)

    assert result.status_code == 503
    assert result.content == {
        "ok": False,
        "available": False,
        "reason": "style_bert_vits2_prepare_failed",
        "message": "初期準備失敗: 実行環境を確認してください。",
        "detail": "missing runtime",
        "setup_hint": "",
        "repo_dir": "/tmp/sbv2/repo",
        "venv_dir": "/tmp/sbv2/venv",
        "python_path": "/tmp/sbv2/venv/bin/python",
        "models_dir": "/tmp/sbv2/models",
    }


def test_sbv2_prepare_main_keeps_audio_runtime_http_error_mapping():
    main_text = MAIN.read_text(encoding="utf-8")
    assert "except AudioRuntimeHttpError as e:" in main_text
    assert "raise HTTPException(status_code=e.status_code, detail=e.detail)" in main_text


def test_sbv2_prepare_runpod_policy_does_not_pass_onnx_or_jit_flags(monkeypatch):
    monkeypatch.setenv("RUNPOD_POD_ID", "pod")
    monkeypatch.setenv("SBV2_ALLOW_ONNX", "1")
    monkeypatch.setenv("SBV2_PREFER_ONNX", "1")
    monkeypatch.setenv("PYTORCH_JIT", "0")
    runtime_results = []

    result = audio_runtime.run_sbv2_prepare_service_body(
        {"model": "koharune-ami"},
        _deps(runtime_results=runtime_results),
    )

    assert result.status_code == 200
    runtime_payload = runtime_results[0]
    assert runtime_payload["model"] == "koharune-ami"
    assert "allow_onnx" not in runtime_payload
    assert "prefer_onnx" not in runtime_payload
    assert "pytorch_jit" not in runtime_payload
    assert "force_pytorch_jit_zero" not in runtime_payload
    assert "dummy_warmup" not in runtime_payload
    assert "warmup" not in runtime_payload
    policy = result.content["sbv2_runtime_policy"]
    assert policy["runtime_profile"] == "runpod"
    assert policy["allow_onnx"] is False
    assert policy["prefer_onnx"] is False
    assert policy["force_pytorch_jit_zero"] is False


def test_sbv2_prepare_uses_policy_device_only_when_request_device_missing(monkeypatch):
    monkeypatch.setenv("STYLE_BERT_VITS2_DEVICE", "cuda:0")
    runtime_results = []

    result = audio_runtime.run_sbv2_prepare_service_body(
        {"model": "koharune-ami"},
        _deps(runtime_results=runtime_results),
    )

    assert result.status_code == 200
    assert runtime_results == [{"model": "koharune-ami", "device": "cuda:0"}]


def test_sbv2_prepare_explicit_device_overrides_policy_device(monkeypatch):
    monkeypatch.setenv("STYLE_BERT_VITS2_DEVICE", "cuda:0")
    runtime_results = []

    result = audio_runtime.run_sbv2_prepare_service_body(
        {"model": "koharune-ami", "device": "cpu"},
        _deps(runtime_results=runtime_results),
    )

    assert result.status_code == 200
    assert runtime_results == [{"model": "koharune-ami", "device": "cpu"}]


def test_sbv2_prepare_policy_resolution_uses_sys_platform():
    text = SERVICE.read_text(encoding="utf-8")
    assert "platform=sys.platform" in text
