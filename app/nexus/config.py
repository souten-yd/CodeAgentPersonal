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
    max_download_mb: int
    max_total_download_mb: int
    max_downloads: int
    download_timeout_sec: int


def _env_bool(name: str, *, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "enabled"}


def _is_runpod_runtime() -> bool:
    # main.py の _is_runpod_runtime() と判定ロジックを必ず同期すること。
    # 判定条件:
    # 1) CODEAGENT_RUNTIME=runpod/rp の明示指定時は Runpod 扱い（ただし /workspace が存在する場合のみ）
    # 2) CODEAGENT_RUNTIME=local/default/docker の明示指定時は非 Runpod
    # 3) それ以外は RUNPOD_POD_ID or RUNPOD_API_KEY があり、かつ /workspace がある場合のみ Runpod
    has_workspace = Path("/workspace").exists()
    has_runpod_env = any(
        (os.environ.get(name) or "").strip()
        for name in ("RUNPOD_POD_ID", "RUNPOD_API_KEY")
    )
    forced = (os.environ.get("CODEAGENT_RUNTIME") or "").strip().lower()
    if forced in {"runpod", "rp"}:
        return has_workspace
    if forced in {"local", "default", "docker"}:
        return False
    return has_runpod_env and has_workspace



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
    is_runpod = _is_runpod_runtime()
    # Runpod 時の既定値を明示しつつ、非 Runpod との後方互換を維持する。
    default_provider = "searxng"
    default_searxng_url = "http://127.0.0.1:8088" if is_runpod else "http://searxng:8080"
    default_search_free_only = True
    default_search_paid_providers_enabled = False

    provider = (
        (os.environ.get("NEXUS_WEB_SEARCH_PROVIDER") or default_provider).strip().lower()
        or default_provider
    )
    searxng_url = (
        (os.environ.get("NEXUS_SEARXNG_URL") or default_searxng_url).strip()
        or default_searxng_url
    )
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
        search_free_only=_env_bool("NEXUS_SEARCH_FREE_ONLY", default=default_search_free_only),
        search_paid_providers_enabled=_env_bool(
            "NEXUS_SEARCH_PAID_PROVIDERS_ENABLED",
            default=default_search_paid_providers_enabled,
        ),
        search_provider_cooldown_sec=_env_int(
            "NEXUS_SEARCH_PROVIDER_COOLDOWN_SEC",
            default=3600,
            minimum=60,
        ),
        brave_search_api_key=(os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip(),
        max_upload_mb=_env_int("NEXUS_MAX_UPLOAD_MB", default=200, minimum=1),
        max_download_mb=_env_int("NEXUS_MAX_DOWNLOAD_MB", default=20, minimum=1),
        max_total_download_mb=_env_int("NEXUS_MAX_TOTAL_DOWNLOAD_MB", default=100, minimum=1),
        max_downloads=_env_int("NEXUS_MAX_DOWNLOADS", default=20, minimum=1),
        download_timeout_sec=_env_int("NEXUS_DOWNLOAD_TIMEOUT_SEC", default=15, minimum=1),
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
