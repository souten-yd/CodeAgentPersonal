import importlib.util
import json
from pathlib import Path

from app.tts import style_bert_vits2_runtime as runtime


_SPEC = importlib.util.spec_from_file_location("main_module", Path(__file__).resolve().parents[1] / "main.py")
main = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(main)


def test_jp_extra_detected_from_config_version(tmp_path, monkeypatch):
    model_id = "sample-jp-extra"
    model_dir = tmp_path / model_id
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps({"version": "2.0-jp-extra", "spk2id": {"A": 0}, "style2id": {"Neutral": 0}}),
        encoding="utf-8",
    )
    (model_dir / "style_vectors.npy").write_bytes(b"dummy")
    (model_dir / "model.safetensors").write_bytes(b"dummy")

    monkeypatch.setattr(main, "_STYLE_BERT_VITS2_MODELS_DIR", str(tmp_path))

    details = main._style_bert_vits2_describe_model(model_id)
    assert details["model_id"] == model_id
    assert details["version"] == "2.0-jp-extra"
    assert details["is_jp_extra"] is True
    assert details["supported_languages"] == ["JP"]


def test_effective_language_forces_jp_on_jp_extra_even_if_english_requested():
    effective, normalized, is_jp_extra = runtime._decide_effective_language("EN", "1.0-jp-extra")
    assert is_jp_extra is True
    assert normalized == "JP"
    assert effective == "JP"


def test_effective_language_keeps_selection_for_global_model():
    effective, normalized, is_jp_extra = runtime._decide_effective_language("EN", "2.0")
    assert is_jp_extra is False
    assert normalized == "EN"
    assert effective == "EN"
