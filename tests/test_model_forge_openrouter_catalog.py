import json
from pathlib import Path

from agent.model_forge import OpenRouterCatalog, OpenRouterConfig


def _models_body(*ids):
    return json.dumps({"data": [{"id": i, "name": i.upper(), "context_length": 32768} for i in ids]})


def _config():
    return OpenRouterConfig(enabled=True, catalog_cache_ttl_seconds=3600)


def test_fetch_normalizes_public_model_metadata() -> None:
    cat = OpenRouterCatalog(_config(), http_get=lambda u, h, t: (200, _models_body("anthropic/claude", "meta/llama")))
    result = cat.get_models()
    assert result.status == "fetched"
    ids = {m.model_id for m in result.models}
    assert ids == {"anthropic/claude", "meta/llama"}
    assert result.models[0].context_window == 32768
    assert result.models[0].provider_id == "openrouter"


def test_ttl_serves_cache_without_refetch_then_force_refresh() -> None:
    now = [1000.0]
    calls = {"n": 0}

    def http_get(u, h, t):
        calls["n"] += 1
        return 200, _models_body("a")

    cat = OpenRouterCatalog(_config(), http_get=http_get, clock=lambda: now[0])
    cat.get_models()
    assert calls["n"] == 1
    now[0] = 1010.0  # within TTL
    cached = cat.get_models()
    assert cached.status == "from_cache"
    assert cached.stale is False
    assert calls["n"] == 1  # no refetch
    cat.get_models(force_refresh=True)
    assert calls["n"] == 2


def test_offline_fallback_serves_stale_cache() -> None:
    state = {"fail": False}

    def http_get(u, h, t):
        if state["fail"]:
            raise ConnectionError("offline")
        return 200, _models_body("a", "b")

    cat = OpenRouterCatalog(_config(), http_get=http_get)
    cat.get_models()  # populate cache
    state["fail"] = True
    result = cat.get_models(force_refresh=True)  # force a fetch that fails
    assert result.status == "from_cache"
    assert result.stale is True
    assert {m.model_id for m in result.models} == {"a", "b"}


def test_no_cache_and_fetch_failure_is_unavailable_not_passed() -> None:
    cat = OpenRouterCatalog(_config(), http_get=lambda u, h, t: (500, "err"))
    result = cat.get_models()
    assert result.status == "unavailable"
    assert result.models == []
    assert result.status != "fetched"


def test_disk_cache_stores_only_public_metadata_no_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-super-secret")
    cache = tmp_path / "catalog" / "openrouter.json"
    cat = OpenRouterCatalog(_config(), http_get=lambda u, h, t: (200, _models_body("a")), cache_path=cache)
    cat.get_models()
    assert cache.exists()
    text = cache.read_text(encoding="utf-8")
    assert "sk-super-secret" not in text  # no secret persisted
    assert "anthropic" in text or '"a"' in text  # public model metadata present


def test_disk_cache_provides_offline_fallback_on_new_instance(tmp_path: Path) -> None:
    cache = tmp_path / "catalog" / "openrouter.json"
    OpenRouterCatalog(_config(), http_get=lambda u, h, t: (200, _models_body("a")), cache_path=cache).get_models()
    # New instance, network down: disk cache is used as a fallback.
    offline = OpenRouterCatalog(
        OpenRouterConfig(enabled=True, catalog_cache_ttl_seconds=0),
        http_get=lambda u, h, t: (_ for _ in ()).throw(ConnectionError("down")),
        cache_path=cache,
    )
    result = offline.get_models()
    assert result.status == "from_cache"
    assert {m.model_id for m in result.models} == {"a"}
