import importlib.util
from pathlib import Path

from app.tts.language_router import resolve_tts_language_route
from app.tts.text_normalizer import normalize_text_for_sbv2_jp_extra

ROOT = Path(__file__).resolve().parents[1]
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")

_SPEC = importlib.util.spec_from_file_location("main_module", ROOT / "main.py")
main = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(main)


def _norm(text: str) -> str:
    return normalize_text_for_sbv2_jp_extra(text, {})["normalized_text"]


def test_ui_removed_legacy_tts_controls():
    forbidden = [
        "TTS Engine",
        "Use TTS Translation",
        "Extra Text Process Options",
        "JP Extra Text Process Options",
        "JP Extra Non Japanese Policy",
    ]
    for label in forbidden:
        assert label not in UI_HTML


def test_ui_payload_always_uses_style_bert_vits2():
    assert "engine: 'style_bert_vits2'" in UI_HTML
    assert "function _normalizeTtsEngine(engine)" in UI_HTML
    assert "return 'style_bert_vits2';" in UI_HTML


def test_server_forces_style_bert_vits2_engine_even_with_legacy_request():
    req = {"engine": "qwen_tts", "engine_key": "legacy_engine", "model": "dummy"}
    out = main.tts_unload_api(req)
    assert out["engine"] == "style_bert_vits2"
    assert out["engine_key"] == "style_bert_vits2"


def test_jp_extra_text_normalization_regression_items():
    assert _norm("これはテストです。次に進みます。") == "これはテストです。次に進みます。"
    assert "😊" not in _norm("了解です😊。次に進みます。")
    assert "https://example.com" not in _norm("詳細は https://example.com を見てください。次に進みます。")
    assert "パイソン" in _norm("Python")
    assert "ファストエーピーアイ" in _norm("FastAPI")
    assert "ギットハブ" in _norm("GitHub")
    assert "ランポッド" in _norm("RunPod")


def test_language_routing_contracts():
    jp_extra = resolve_tts_language_route({"text": "hello", "echo_output_language": "en", "echo_tts_language": "en"}, "2.0-jp-extra")
    assert jp_extra["tts_language"] == "ja"
    assert jp_extra["needs_translation"] is True
    assert jp_extra["translation_target_language"] == "ja"

    global_en = resolve_tts_language_route({"text": "hello", "echo_output_language": "en", "echo_tts_language": "en"}, "global")
    assert global_en["needs_translation"] is False

    global_ja_to_en = resolve_tts_language_route({"text": "こんにちは", "echo_output_language": "ja", "echo_tts_language": "en"}, "global")
    assert global_ja_to_en["needs_translation"] is True
    assert global_ja_to_en["translation_target_language"] == "en"


def test_preview_returns_all_required_text_stages(tmp_path, monkeypatch):
    model_id = "sample-jp-extra"
    model_dir = tmp_path / model_id
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"version":"2.0-jp-extra","spk2id":{"A":0},"style2id":{"Neutral":0}}', encoding="utf-8")
    (model_dir / "style_vectors.npy").write_bytes(b"dummy")
    (model_dir / "model.safetensors").write_bytes(b"dummy")

    from app.tts import style_bert_vits2_runtime as runtime

    rt = runtime.StyleBertVITS2Runtime()
    monkeypatch.setattr(runtime, "_resolve_model_paths", lambda _m: (str(model_dir / "model.safetensors"), str(model_dir / "config.json"), str(model_dir / "style_vectors.npy")))
    monkeypatch.setattr(runtime, "_resolve_sbv2_jp_extra_normalization_settings", lambda _req, *, is_jp_extra: {})

    preview = rt.build_normalization_preview({
        "model": model_id,
        "language": "JP",
        "raw_text": "Hello!! https://example.com です。",
        "translated_text": "ハロー！！ https://example.com です。",
        "use_translation": True,
        "text_source": "translated",
        "needs_translation": True,
        "translation_target_language": "ja",
        "route_info": {"source_language": "en", "output_language": "ja", "tts_language": "ja", "model_kind": "jp_extra"},
    })

    assert preview["original_text"]
    assert preview["after_translation"]
    assert preview["after_tts_normalization"]
    assert preview["final_text_sent_to_style_bert_vits2"]


def test_apply_tts_language_routing_uses_translation_target_language(monkeypatch):
    calls = []

    def _fake_translate(text, *, source_language, target_language):
        calls.append((text, source_language, target_language))
        return f"{text}:{target_language}"

    monkeypatch.setattr(main, "_translate_text_for_tts", _fake_translate)

    req_jp_extra = {"text": "hello", "echo_output_language": "en", "echo_tts_language": "en"}
    main._apply_tts_language_routing(req_jp_extra, model_version="2.0-jp-extra")
    assert calls[-1][2] == "ja"

    req_global_ja_to_en = {"text": "こんにちは", "echo_output_language": "ja", "echo_tts_language": "en"}
    main._apply_tts_language_routing(req_global_ja_to_en, model_version="global")
    assert calls[-1][2] == "en"

    req_global_en_to_ja = {"text": "hello", "echo_output_language": "en", "echo_tts_language": "ja"}
    main._apply_tts_language_routing(req_global_en_to_ja, model_version="global")
    assert calls[-1][2] == "ja"


def test_apply_tts_language_routing_skip_prepared_text(monkeypatch):
    called = {"v": False}

    def _fake_translate(*args, **kwargs):
        called["v"] = True
        return "x"

    monkeypatch.setattr(main, "_translate_text_for_tts", _fake_translate)
    req = {
        "text": "prepared",
        "text_prepared_for_tts": True,
        "skip_tts_language_routing": True,
        "prepared_tts_language": "ja",
        "echo_output_language": "en",
        "echo_tts_language": "ja",
    }
    main._apply_tts_language_routing(req, model_version="global")
    assert called["v"] is False
    assert req["text_source"] == "prepared"


def test_build_payload_jp_extra_forces_jp_language_without_nameerror(tmp_path, monkeypatch):
    from app.tts import style_bert_vits2_runtime as runtime

    model_dir = tmp_path / "sample-jp-extra"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"version":"2.0-jp-extra"}', encoding="utf-8")
    (model_dir / "style_vectors.npy").write_bytes(b"dummy")
    (model_dir / "model.safetensors").write_bytes(b"dummy")

    monkeypatch.setattr(runtime, "_resolve_model_paths", lambda _m: (str(model_dir / "model.safetensors"), str(model_dir / "config.json"), str(model_dir / "style_vectors.npy")))

    rt = runtime.StyleBertVITS2Runtime()
    payload = rt._build_payload({"language": "en", "tts_language": "en"}, model="sample-jp-extra", text="hello", request_id="t1")
    assert payload["is_jp_extra"] is True
    assert payload["effective_language"] == "JP"


def test_build_payload_global_respects_route_tts_language(tmp_path, monkeypatch):
    from app.tts import style_bert_vits2_runtime as runtime

    model_dir = tmp_path / "sample-global"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"version":"2.0"}', encoding="utf-8")
    (model_dir / "style_vectors.npy").write_bytes(b"dummy")
    (model_dir / "model.safetensors").write_bytes(b"dummy")

    monkeypatch.setattr(runtime, "_resolve_model_paths", lambda _m: (str(model_dir / "model.safetensors"), str(model_dir / "config.json"), str(model_dir / "style_vectors.npy")))

    rt = runtime.StyleBertVITS2Runtime()
    payload_en = rt._build_payload({"route_info": {"tts_language": "en"}}, model="sample-global", text="hello", request_id="t2")
    payload_ja = rt._build_payload({"route_info": {"tts_language": "ja"}}, model="sample-global", text="こんにちは", request_id="t3")
    assert payload_en["effective_language"] == "EN"
    assert payload_ja["effective_language"] == "JP"


def test_preview_uses_same_language_resolution(tmp_path, monkeypatch):
    from app.tts import style_bert_vits2_runtime as runtime

    model_dir = tmp_path / "sample-global"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"version":"2.0"}', encoding="utf-8")
    (model_dir / "style_vectors.npy").write_bytes(b"dummy")
    (model_dir / "model.safetensors").write_bytes(b"dummy")

    monkeypatch.setattr(runtime, "_resolve_model_paths", lambda _m: (str(model_dir / "model.safetensors"), str(model_dir / "config.json"), str(model_dir / "style_vectors.npy")))

    rt = runtime.StyleBertVITS2Runtime()
    preview = rt.build_normalization_preview({"model": "sample-global", "route_info": {"tts_language": "en"}, "raw_text": "hello"})
    assert preview["effective_language"] == "EN"
