from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal


MemoryScope = Literal["short", "long", "auto"]


class MemoryStore:
    """エージェント記憶の読み書きインターフェース。"""

    def recall(self, objective: str, limit: int = 5) -> list[dict]:
        raise NotImplementedError

    def save(self, item: dict) -> None:
        raise NotImplementedError


class HybridMemoryStore(MemoryStore):
    """short-term(リングバッファ) と long-term(SQLite アダプタ) を扱うメモリ実装。"""

    def __init__(
        self,
        short_term_limit: int = 64,
        long_term_saver: Callable[[dict], str | None] | None = None,
        long_term_searcher: Callable[[str, int], list[dict]] | None = None,
    ) -> None:
        self._short_term: deque[dict[str, Any]] = deque(maxlen=max(1, short_term_limit))
        self._long_term_saver = long_term_saver
        self._long_term_searcher = long_term_searcher

    def save(self, item: dict) -> None:
        self.store_memory(key=item.get("key", "entry"), value=item, scope="long")

    def recall(self, objective: str, limit: int = 5) -> list[dict]:
        return self.retrieve_memory(query=objective, scope="auto", limit=limit)

    def store_memory(self, key: str, value: Any, scope: Literal["short", "long"] = "short") -> str | None:
        record = {
            "key": key,
            "value": self._to_serializable(value),
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }

        if scope == "short":
            self._short_term.append(record)
            return None

        if not self._long_term_saver:
            return None

        entry = self._to_long_term_entry(record)
        return self._long_term_saver(entry)

    def retrieve_memory(self, query: str, scope: MemoryScope = "auto", limit: int = 5) -> list[dict]:
        bounded_limit = max(1, int(limit))
        if scope == "short":
            return self._search_short_term(query=query, limit=bounded_limit)
        if scope == "long":
            return self._search_long_term(query=query, limit=bounded_limit)

        short_hits = self._search_short_term(query=query, limit=bounded_limit)
        if len(short_hits) >= bounded_limit:
            return short_hits[:bounded_limit]
        long_hits = self._search_long_term(query=query, limit=bounded_limit)
        return (short_hits + long_hits)[:bounded_limit]

    def _search_short_term(self, query: str, limit: int) -> list[dict]:
        hay_query = (query or "").lower().strip()
        records = list(self._short_term)
        if not hay_query:
            return records[-limit:][::-1]

        hits: list[dict] = []
        for item in reversed(records):
            text = f"{item.get('key', '')} {item.get('value', '')}".lower()
            if hay_query in text:
                hits.append(item)
                if len(hits) >= limit:
                    break
        return hits

    def _search_long_term(self, query: str, limit: int) -> list[dict]:
        if not self._long_term_searcher:
            return []
        return self._long_term_searcher(query, limit)

    def _to_long_term_entry(self, record: dict[str, Any]) -> dict[str, Any]:
        content = str(record["value"])
        title = str(record["key"])[:120] or "agent-memory"
        return {
            "category": "agent_loop",
            "title": title,
            "content": content,
            "keywords": ["agent", "loop", "summary"],
        }

    def _to_serializable(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, list):
            return [self._to_serializable(v) for v in value]
        if isinstance(value, dict):
            return {k: self._to_serializable(v) for k, v in value.items()}
        return value
