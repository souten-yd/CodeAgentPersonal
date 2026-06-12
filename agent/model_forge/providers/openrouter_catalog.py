"""OpenRouter model catalog fetch + TTL cache with offline fallback (PFG-11).

Fetches the public OpenRouter models list, normalizes it into Forge ModelDescriptors,
and caches it with a TTL. Only public model metadata is stored — never secrets. When a
fresh fetch fails, the last cached catalog is served as a stale fallback; when there is
no cache at all, the result is reported as "unavailable" (never silently passed as a
successful fetch). The HTTP transport is injectable so tests run offline.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent.model_forge.providers.openrouter_config import OpenRouterConfig, build_openrouter_headers
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel, ModelDescriptor, SourceClass

# (url, headers, timeout) -> (status, body). Must raise TimeoutError/ConnectionError on
# network problems.
HttpGet = Callable[[str, dict, float], "tuple[int, str]"]


class OpenRouterCatalogResult(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    status: str  # "fetched" | "from_cache" | "unavailable"
    models: list[ModelDescriptor] = []
    fetched_at: str = ""
    stale: bool = False
    error: str = ""


def _default_http_get(url: str, headers: dict, timeout: float) -> "tuple[int, str]":
    import socket
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
            raise TimeoutError(str(reason)) from exc
        raise ConnectionError(str(reason)) from exc


def _normalize_models(body: str) -> list[ModelDescriptor]:
    data = json.loads(body)
    raw = data.get("data") if isinstance(data, dict) else data
    models: list[ModelDescriptor] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("id") or "").strip()
        if not model_id:
            continue
        models.append(ModelDescriptor(
            model_id=model_id,
            provider_id="openrouter",
            display_name=str(entry.get("name") or model_id),
            source_class=SourceClass.EXTERNAL_CLOUD,
            context_window=int(entry.get("context_length") or 0),
            capability_tags=[],
        ))
    return models


class OpenRouterCatalog:
    def __init__(
        self,
        config: OpenRouterConfig | None = None,
        *,
        http_get: HttpGet | None = None,
        cache_path: str | Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config or OpenRouterConfig()
        self._http_get = http_get or _default_http_get
        self._cache_path = Path(cache_path) if cache_path else None
        self._clock = clock
        self._cache: OpenRouterCatalogResult | None = None
        self._cache_monotonic: float | None = None
        self._load_disk_cache()

    def get_models(self, *, force_refresh: bool = False) -> OpenRouterCatalogResult:
        if not force_refresh and self._cache is not None and self._cache_monotonic is not None:
            age = self._clock() - self._cache_monotonic
            if age < max(0, self.config.catalog_cache_ttl_seconds):
                return self._cache.model_copy(update={"status": "from_cache", "stale": False})
        endpoint = f"{self.config.base_url.rstrip('/')}/models"
        headers = build_openrouter_headers(self.config)
        try:
            status, body = self._http_get(endpoint, headers, self.config.request_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — fetch failure must not crash.
            return self._fallback(f"fetch_error:{type(exc).__name__}")
        if status != 200:
            return self._fallback(f"http_{status}")
        try:
            models = _normalize_models(body)
        except Exception:  # noqa: BLE001
            return self._fallback("malformed_catalog")
        result = OpenRouterCatalogResult(
            status="fetched", models=models, fetched_at=datetime.now(timezone.utc).isoformat(), stale=False,
        )
        self._cache = result
        self._cache_monotonic = self._clock()
        self._write_disk_cache(result)
        return result

    def _fallback(self, error: str) -> OpenRouterCatalogResult:
        if self._cache is not None:
            # Offline fallback: serve the last known catalog, clearly marked stale.
            return self._cache.model_copy(update={"status": "from_cache", "stale": True, "error": error})
        return OpenRouterCatalogResult(status="unavailable", models=[], error=error)

    def _load_disk_cache(self) -> None:
        if self._cache_path is None or not self._cache_path.exists():
            return
        try:
            cached = OpenRouterCatalogResult.model_validate_json(self._cache_path.read_text(encoding="utf-8"))
            self._cache = cached.model_copy(update={"status": "from_cache"})
            self._cache_monotonic = self._clock()  # treat disk cache as just-loaded for TTL
        except Exception:  # noqa: BLE001 — a corrupt cache is simply ignored.
            self._cache = None

    def _write_disk_cache(self, result: OpenRouterCatalogResult) -> None:
        if self._cache_path is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Public model metadata only — no secrets are ever part of this result.
            self._cache_path.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 — cache write failure is non-fatal.
            return
