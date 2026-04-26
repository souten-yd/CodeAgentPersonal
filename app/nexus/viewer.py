from __future__ import annotations

from pathlib import Path

from app.nexus.db import get_conn


def get_source_body(source_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT source_id, title, url, local_text_path, local_markdown_path FROM nexus_sources WHERE source_id = ?",
            (source_id,),
        ).fetchone()

    if row is None:
        raise ValueError("source not found")

    for key in ("local_markdown_path", "local_text_path"):
        path_str = str(row[key] or "").strip()
        if not path_str:
            continue
        path = Path(path_str)
        if path.exists() and path.is_file():
            return {
                "source_id": row["source_id"],
                "title": str(row["title"] or ""),
                "url": str(row["url"] or ""),
                "content": path.read_text(encoding="utf-8", errors="ignore"),
                "path": str(path),
            }

    return {
        "source_id": row["source_id"],
        "title": str(row["title"] or ""),
        "url": str(row["url"] or ""),
        "content": "",
        "path": "",
    }


def extract_snippet(content: str, query: str, *, window: int = 180) -> str:
    raw_content = content or ""
    token = (query or "").strip()
    if not raw_content or not token:
        return raw_content[: window * 2]
    idx = raw_content.lower().find(token.lower())
    if idx < 0:
        return raw_content[: window * 2]
    start = max(0, idx - window)
    end = min(len(raw_content), idx + len(token) + window)
    return raw_content[start:end]
