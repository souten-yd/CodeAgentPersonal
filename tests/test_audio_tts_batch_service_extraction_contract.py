from pathlib import Path
from types import SimpleNamespace
import io
import wave

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


def _wav_bytes(sample_rate: int = 24000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * 4)
    return out.getvalue()


def test_batch_service_symbols_exist_and_audio_runtime_stays_route_neutral():
    assert hasattr(audio_runtime, "run_tts_synthesize_batch_service_body")
    assert callable(audio_runtime.run_tts_synthesize_batch_service_body)
    assert hasattr(audio_runtime, "TtsSynthesizeBatchServiceDependencies")

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


def test_batch_and_high_risk_route_owners_remain_main():
    expected_main_routes = [
        ("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api"),
        ("/tts/synthesize", "POST", "tts_synthesize_api"),
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
    assert '@app.post("/tts/synthesize-batch")' in main_text
    assert "run_tts_synthesize_batch_service_body" in main_text
    assert "TtsSynthesizeBatchServiceDependencies" in main_text


class _DummyRuntime:
    def __init__(self, *, fail=None):
        self.fail = fail
        self.prepared = []
        self.seen = []

    def prepare(self, payload):
        self.prepared.append(dict(payload))

    def synthesize(self, payload):
        self.seen.append(dict(payload))
        if self.fail is not None:
            raise self.fail
        return _wav_bytes(), "audio/wav"


class _DummyRegistry:
    def __init__(self, runtime):
        self.runtime = runtime

    def resolve_engine_key(self, raw_engine_key, requested_engine_key=None):
        assert raw_engine_key == "style_bert_vits2"
        assert requested_engine_key == "style_bert_vits2"
        return "style_bert_vits2"

    def get(self, raw_engine=None, raw_engine_key=None):
        assert raw_engine == "style_bert_vits2"
        assert raw_engine_key == "style_bert_vits2"
        return self.runtime


def _deps(runtime, *, steps=None, status_updates=None):
    steps = steps if steps is not None else []
    status_updates = status_updates if status_updates is not None else []
    return audio_runtime.TtsSynthesizeBatchServiceDependencies(
        engine_registry=_DummyRegistry(runtime),
        logger=SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        ensure_model_exists=lambda model, models_dir: None,
        style_bert_vits2_models_dir="/tmp/sbv2-models",
        request_id_factory=lambda: "batch-fixed",
        job_create=lambda **kwargs: "job-fixed",
        job_update_status=lambda project, job_id, status: status_updates.append((project, job_id, status)),
        job_append_step=lambda project, job_id, seq, event_type, data: steps.append(
            (project, job_id, seq, event_type, dict(data))
        ),
        sample_rate_from_wav_bytes=lambda audio: 24000,
        merge_wav_bytes=lambda chunks: chunks[0] if chunks else b"",
        perf_counter=lambda: 1.0,
    )


def test_batch_service_uses_dependency_injection_and_preserves_json_shape():
    steps = []
    status_updates = []
    runtime = _DummyRuntime()
    result = audio_runtime.run_tts_synthesize_batch_service_body(
        {
            "items": [
                {"id": "a", "text": " hello "},
                {"id": "b", "text": "world"},
            ],
            "project": "demo",
        },
        _deps(runtime, steps=steps, status_updates=status_updates),
    )

    assert list(result.keys()) == ["request_id", "engine", "model", "device", "project", "job_id", "items"]
    assert result["request_id"] == "batch-fixed"
    assert result["engine"] == "style_bert_vits2"
    assert result["model"] == "koharune-ami"
    assert result["project"] == "demo"
    assert result["job_id"] == "job-fixed"
    assert [item["id"] for item in result["items"]] == ["a", "b"]
    assert all("audio_base64" in item for item in result["items"])
    assert runtime.prepared == [{"model": "koharune-ami", "device": ""}]
    assert [payload["request_id"] for payload in runtime.seen] == ["batch-fixed-001", "batch-fixed-002"]
    assert [event for *_prefix, event, _data in steps] == [
        "tts_batch_started",
        "tts_batch_item_started",
        "tts_batch_item_done",
        "tts_batch_item_started",
        "tts_batch_item_done",
        "tts_batch_done",
    ]
    assert status_updates == [("demo", "job-fixed", "running"), ("demo", "job-fixed", "done")]


def test_batch_service_preserves_http_error_mapping():
    try:
        audio_runtime.run_tts_synthesize_batch_service_body(
            {"items": []},
            _deps(_DummyRuntime()),
        )
    except audio_runtime.AudioRuntimeHttpError as exc:
        assert exc.status_code == 400
        assert exc.detail == "items must be a non-empty list"
    else:
        raise AssertionError("expected AudioRuntimeHttpError")

    payload = '{"status_code":422,"error":"bad text","text_preview":"x","effective_language":"JP","model_version":"2.0"}'
    try:
        audio_runtime.run_tts_synthesize_batch_service_body(
            {"items": [{"text": "x"}]},
            _deps(_DummyRuntime(fail=ValueError(payload))),
        )
    except audio_runtime.AudioRuntimeHttpError as exc:
        assert exc.status_code == 422
        assert exc.detail == {
            "error": "bad text",
            "text_preview": "x",
            "effective_language": "JP",
            "model_version": "2.0",
        }
    else:
        raise AssertionError("expected AudioRuntimeHttpError")
