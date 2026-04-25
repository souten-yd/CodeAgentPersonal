from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path



def ensure_dir(path: Path) -> Path:
    """ディレクトリが存在しなければ作成して返す。"""
    path.mkdir(parents=True, exist_ok=True)
    return path



def now_utc_iso() -> str:
    """UTCのISO-8601文字列を返す。"""
    return datetime.now(timezone.utc).isoformat()
