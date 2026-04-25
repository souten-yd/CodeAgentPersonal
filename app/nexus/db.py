from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.nexus.config import NEXUS_PATHS
from app.nexus.utils import ensure_dir


REQUIRED_DIRS: tuple[Path, ...] = (
    NEXUS_PATHS.nexus_dir,
    NEXUS_PATHS.uploads_dir,
    NEXUS_PATHS.extracted_dir,
    NEXUS_PATHS.reports_dir,
    NEXUS_PATHS.exports_dir,
)



def initialize_storage() -> Path:
    """`CA_DATA_DIR/nexus/nexus.db` と必要ディレクトリを初期化する。"""
    ensure_dir(NEXUS_PATHS.ca_data_dir)
    for directory in REQUIRED_DIRS:
        ensure_dir(directory)

    with sqlite3.connect(NEXUS_PATHS.db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.commit()

    return NEXUS_PATHS.db_path


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Nexus DB接続（空実装の最小形）。"""
    initialize_storage()
    conn = sqlite3.connect(NEXUS_PATHS.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


DB_PATH = NEXUS_PATHS.db_path

# import時に初期化
initialize_storage()
