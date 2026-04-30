import json
import threading

from app.tts import katakanaizer


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"x"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _mock_llm_response(mapping: dict[str, str]):
    return {
        "choices": [
            {"message": {"content": json.dumps(mapping, ensure_ascii=False)}}
        ]
    }


def test_persistent_cache_hit_without_llm(monkeypatch, tmp_path):
    cache_path = tmp_path / "katakana_cache.json"
    monkeypatch.setenv("CODEAGENT_KATAKANA_CACHE_PATH", str(cache_path))
    katakanaizer._PERSISTENT_CACHE = katakanaizer.KatakanaPersistentCache()
    katakanaizer._PERSISTENT_CACHE.set("Python", "パイソン")

    called = {"n": 0}

    def _boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("llm should not be called")

    monkeypatch.setattr(katakanaizer.requests, "post", _boom)
    out = katakanaizer.katakanaize_english_segments_with_llm(["python"])
    assert out["python"] == "パイソン"
    assert called["n"] == 0


def test_save_and_reuse_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "katakana_cache.json"
    monkeypatch.setenv("CODEAGENT_KATAKANA_CACHE_PATH", str(cache_path))
    katakanaizer._KATAKANA_CACHE.clear()
    katakanaizer._PERSISTENT_CACHE = katakanaizer.KatakanaPersistentCache()
    calls = {"n": 0}

    def _mock_post(*args, **kwargs):
        calls["n"] += 1
        return _DummyResponse(_mock_llm_response({"FastAPI": "ファストエーピーアイ"}))

    monkeypatch.setattr(katakanaizer.requests, "post", _mock_post)
    first = katakanaizer.katakanaize_english_segments_with_llm(["FastAPI"])
    assert first["FastAPI"] == "ファストエーピーアイ"
    assert cache_path.exists()

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["entries"]["fastapi"]["reading"] == "ファストエーピーアイ"

    katakanaizer._KATAKANA_CACHE.clear()
    katakanaizer._PERSISTENT_CACHE = katakanaizer.KatakanaPersistentCache()
    second = katakanaizer.katakanaize_english_segments_with_llm(["FASTAPI"])
    assert second["FASTAPI"] == "ファストエーピーアイ"
    assert calls["n"] == 1


def test_broken_json_does_not_crash(monkeypatch, tmp_path):
    cache_path = tmp_path / "katakana_cache.json"
    cache_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("CODEAGENT_KATAKANA_CACHE_PATH", str(cache_path))
    katakanaizer._PERSISTENT_CACHE = katakanaizer.KatakanaPersistentCache()

    monkeypatch.setattr(
        katakanaizer.requests,
        "post",
        lambda *args, **kwargs: _DummyResponse(_mock_llm_response({"FastAPI": "ファストエーピーアイ"})),
    )
    out = katakanaizer.katakanaize_english_segments_with_llm(["FastAPI"])
    assert out["FastAPI"] == "ファストエーピーアイ"


def test_invalid_llm_value_not_persisted(monkeypatch, tmp_path):
    cache_path = tmp_path / "katakana_cache.json"
    monkeypatch.setenv("CODEAGENT_KATAKANA_CACHE_PATH", str(cache_path))
    katakanaizer._KATAKANA_CACHE.clear()
    katakanaizer._PERSISTENT_CACHE = katakanaizer.KatakanaPersistentCache()
    monkeypatch.setattr(
        katakanaizer.requests,
        "post",
        lambda *args, **kwargs: _DummyResponse(_mock_llm_response({"FastAPI": "http://example.com"})),
    )
    out = katakanaizer.katakanaize_english_segments_with_llm(["FastAPI"])
    assert out["FastAPI"] == "FastAPI"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "fastapi" not in payload["entries"]


def test_parallel_save_not_broken(monkeypatch, tmp_path):
    cache_path = tmp_path / "katakana_cache.json"
    monkeypatch.setenv("CODEAGENT_KATAKANA_CACHE_PATH", str(cache_path))
    katakanaizer._KATAKANA_CACHE.clear()
    katakanaizer._PERSISTENT_CACHE = katakanaizer.KatakanaPersistentCache()

    def _mock_post(*args, **kwargs):
        segments = json.loads(kwargs["json"]["messages"][1]["content"])["segments"]
        return _DummyResponse(_mock_llm_response({s: "テスト" for s in segments}))

    monkeypatch.setattr(katakanaizer.requests, "post", _mock_post)

    def _run(i):
        katakanaizer.katakanaize_english_segments_with_llm([f"Word{i}"])

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 10
