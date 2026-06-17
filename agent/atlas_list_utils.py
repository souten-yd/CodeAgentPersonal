"""Shared list helpers (consolidated exact-duplicate _as_str_list)."""
from __future__ import annotations

def as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
