import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import main


def test_tts_synthesize_uses_runtime_and_writes_debug(monkeypatch):
    calls = {"stages": [], "runtime_called": False}

    class DummyRuntime:
        def synthesize(self, req):
            calls["runtime_called"] = True
            main._write_tts_debug_entry(
                {
                    "stage": "runtime_enter",
                    "request_id": req["request_id"],
                    "model": req.get("model"),
                    "model_path": "/dummy/model",
                    "normalized_text": req.get("text"),
                    "device": "cpu",
                    "caller": req.get("caller") or "manual",
                }
            )
            main._write_tts_debug_entry(
                {
                    "stage": "runtime_success",
                    "request_id": req["request_id"],
                    "model_name": req.get("model"),
                    "model_path": "/dummy/model",
                    "normalized_text": req.get("text"),
                    "infer_kwargs_keys": ["style"],
                    "device": "cpu",
                    "encoder": "soundfile",
                    "sample_rate": 44100,
                    "audio_dtype": "int16",
                    "audio_shape": [1, 2],
                    "audio_min": -0.1,
                    "audio_max": 0.1,
                    "wav_bytes_len": 8,
                }
            )
            return b"RIFFxxxx", "audio/wav"

    monkeypatch.setattr(main, "ensure_model_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_read_model_version", lambda *args, **kwargs: "JP-Extra")
    monkeypatch.setattr(main, "_apply_tts_language_routing", lambda req, model_version=None: "jp_extra_direct")

    def fake_debug(entry):
        calls["stages"].append(entry.get("stage"))

    monkeypatch.setattr(main, "_write_tts_debug_entry", fake_debug)
    monkeypatch.setattr(main._tts_engine_registry, "get", lambda **kwargs: DummyRuntime())

    resp = main.tts_synthesize_api({"text": "テスト", "engine": "legacy", "model": "koharune-ami"})

    assert resp.media_type == "audio/wav"
    assert calls["runtime_called"] is True
    assert "route_enter" in calls["stages"]
    assert "runtime_enter" in calls["stages"]
    assert "runtime_success" in calls["stages"]


def test_tts_synthesize_registry_get_forced_style_bert_vits2(monkeypatch):
    captured = {}

    class DummyRuntime:
        def synthesize(self, req):
            return b"RIFFxxxx", "audio/wav"

    monkeypatch.setattr(main, "ensure_model_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_read_model_version", lambda *args, **kwargs: "JP-Extra")
    monkeypatch.setattr(main, "_apply_tts_language_routing", lambda req, model_version=None: "jp_extra_direct")
    monkeypatch.setattr(main, "_write_tts_debug_entry", lambda entry: None)

    def fake_get(**kwargs):
        captured.update(kwargs)
        return DummyRuntime()

    monkeypatch.setattr(main._tts_engine_registry, "get", fake_get)

    main.tts_synthesize_api({"text": "abc", "engine": "qwen_tts", "engine_key": "legacy"})

    assert captured == {"raw_engine_key": "style_bert_vits2"}
