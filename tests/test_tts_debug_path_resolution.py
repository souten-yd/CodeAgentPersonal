import importlib.util
from pathlib import Path

from app.tts import tts_debug

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("main_module", ROOT / "main.py")
main = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(main)


def test_ca_data_dir_shared_between_runtime_write_and_main_read(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CODEAGENT_TTS_DEBUG_LOG_PATH", raising=False)
    tts_debug.write_tts_debug_entry({"request_id": "r1", "ok": True})
    entries = main._read_recent_tts_debug_entries(5)
    assert entries and entries[-1]["request_id"] == "r1"
    assert tts_debug.resolve_tts_debug_log_path() == tmp_path / "tts_debug.jsonl"


def test_tts_debug_log_path_env_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path / "ca_data"))
    explicit = tmp_path / "explicit" / "debug.jsonl"
    monkeypatch.setenv("CODEAGENT_TTS_DEBUG_LOG_PATH", str(explicit))
    assert tts_debug.resolve_tts_debug_log_path() == explicit


def test_runpod_path_selected_when_detected(monkeypatch):
    monkeypatch.delenv("CODEAGENT_TTS_DEBUG_LOG_PATH", raising=False)
    monkeypatch.delenv("CODEAGENT_CA_DATA_DIR", raising=False)
    monkeypatch.setattr(tts_debug, "_is_runpod_runtime", lambda: True)
    assert tts_debug.resolve_tts_debug_log_path() == Path("/workspace/ca_data/tts_debug.jsonl")


def test_read_returns_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_DEBUG_LOG_PATH", str(tmp_path / "missing.jsonl"))
    assert tts_debug.read_recent_tts_debug_entries(20) == []


def test_read_survives_invalid_jsonl_line(tmp_path, monkeypatch):
    path = tmp_path / "debug.jsonl"
    path.write_text('{"ok":true}\nnot-json\n', encoding="utf-8")
    monkeypatch.setenv("CODEAGENT_TTS_DEBUG_LOG_PATH", str(path))
    rows = tts_debug.read_recent_tts_debug_entries(20)
    assert rows[0]["ok"] is True
    assert rows[1]["error"] == "invalid_jsonl_entry"


def test_debug_tts_api_returns_json_on_read_error(monkeypatch):
    def _boom(_limit=20):
        return [{"ok": False, "error": "boom", "traceback": "tb"}]

    monkeypatch.setattr(main, "_read_recent_tts_debug_entries", _boom)
    out = main.tts_debug_api(limit=5)
    assert out["ok"] is False
    assert out["entries"] == []
    assert out["error"] == "boom"


def test_no_onnxruntime_dependency_added():
    req = Path("requirements.txt")
    if req.exists():
        txt = req.read_text(encoding="utf-8").lower()
        assert "onnxruntime-directml" not in txt
        assert "onnxruntime" not in txt
    docker = Path("Dockerfile")
    if docker.exists():
        txt = docker.read_text(encoding="utf-8").lower()
        assert "onnxruntime-directml" not in txt
        assert "onnxruntime" not in txt
