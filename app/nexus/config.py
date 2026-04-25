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
