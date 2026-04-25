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
    brave_search_api_key: str


def _env_bool(name: str, *, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "enabled"}


def load_runtime_config() -> NexusRuntimeConfig:
    """環境変数から Nexus 実行時設定をロードする。"""
    provider = (os.environ.get("NEXUS_WEB_SEARCH_PROVIDER") or "brave").strip().lower()
    return NexusRuntimeConfig(
        enable_web=_env_bool("NEXUS_ENABLE_WEB", default=True),
        enable_news=_env_bool("NEXUS_ENABLE_NEWS", default=True),
        enable_market=_env_bool("NEXUS_ENABLE_MARKET", default=True),
        web_search_provider=provider or "brave",
        brave_search_api_key=(os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip(),
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
