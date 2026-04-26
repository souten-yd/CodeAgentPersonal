from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NexusPaths:
    """Nexus が利用する永続化パス群。"""

    ca_data_dir: Path
    nexus_dir: Path
    db_path: Path
    uploads_dir: Path
    extracted_dir: Path
    reports_dir: Path
    exports_dir: Path


@dataclass(frozen=True)
class NexusRuntimeConfig:
    """Nexus の実行時フラグ/プロバイダ設定。"""

    enable_web: bool
    enable_news: bool
    enable_market: bool
    web_search_provider: str
    searxng_url: str
    search_fallback_providers: tuple[str, ...]
    search_free_only: bool
    search_paid_providers_enabled: bool
    search_provider_cooldown_sec: int
    brave_search_api_key: str
    max_upload_mb: int


def _env_bool(name: str, *, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "enabled"}



def _env_csv(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return values or default

def _env_int(name: str, *, default: int, minimum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def load_runtime_config() -> NexusRuntimeConfig:
    """環境変数から Nexus 実行時設定をロードする。"""
    provider = (os.environ.get("NEXUS_WEB_SEARCH_PROVIDER") or "searxng").strip().lower() or "searxng"
    searxng_url = (os.environ.get("NEXUS_SEARXNG_URL") or "http://searxng:8080").strip() or "http://searxng:8080"
    return NexusRuntimeConfig(
        enable_web=_env_bool("NEXUS_ENABLE_WEB", default=True),
        enable_news=_env_bool("NEXUS_ENABLE_NEWS", default=True),
        enable_market=_env_bool("NEXUS_ENABLE_MARKET", default=True),
        web_search_provider=provider,
        searxng_url=searxng_url,
        search_fallback_providers=_env_csv(
            "NEXUS_SEARCH_FALLBACK_PROVIDERS",
            default=("searxng",),
        ),
        search_free_only=_env_bool("NEXUS_SEARCH_FREE_ONLY", default=True),
        search_paid_providers_enabled=_env_bool("NEXUS_SEARCH_PAID_PROVIDERS_ENABLED", default=False),
        search_provider_cooldown_sec=_env_int(
            "NEXUS_SEARCH_PROVIDER_COOLDOWN_SEC",
            default=3600,
            minimum=60,
        ),
        brave_search_api_key=(os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip(),
        max_upload_mb=_env_int("NEXUS_MAX_UPLOAD_MB", default=200, minimum=1),
    )


def resolve_ca_data_dir() -> Path:
    """`CODEAGENT_CA_DATA_DIR` またはデフォルト `./ca_data` を返す。"""
    base_dir = Path(__file__).resolve().parents[2]
    default_ca_data = base_dir / "ca_data"
    return Path(os.environ.get("CODEAGENT_CA_DATA_DIR", str(default_ca_data))).resolve()


def build_nexus_paths() -> NexusPaths:
    """Nexus 配下の主要ディレクトリ構成を生成する。"""
    ca_data_dir = resolve_ca_data_dir()
    nexus_dir = ca_data_dir / "nexus"

    return NexusPaths(
        ca_data_dir=ca_data_dir,
        nexus_dir=nexus_dir,
        db_path=nexus_dir / "nexus.db",
        uploads_dir=nexus_dir / "uploads",
        extracted_dir=nexus_dir / "extracted",
        reports_dir=nexus_dir / "reports",
        exports_dir=nexus_dir / "exports",
    )


NEXUS_PATHS = build_nexus_paths()
