from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal


MemoryScope = Literal["short", "long", "auto"]


@dataclass(slots=True)
class ArchitectureDecision:
    epic: str
    decision: str
    rationale: str
    alternatives: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    related_modules: list[str] = field(default_factory=list)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class TaskOutcome:
    task_id: str
    task_title: str
    epic: str = ""
    what_changed: list[str] = field(default_factory=list)
    why: str = ""
    verification: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class ModuleMap:
    module: str
    responsibilities: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class RiskRegister:
    risk_id: str
    epic: str
    description: str
    impact: str = "medium"
    likelihood: str = "medium"
    mitigation: str = ""
    owner: str = "agent"
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
        self._session_task_outcomes: list[TaskOutcome] = []

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
        normalized_query = (query or "").strip()
        effective_query = normalized_query or "project brief latest handoff"
        if scope == "short":
            return self._search_short_term(query=normalized_query, limit=bounded_limit)
        if scope == "long":
            long_hits = self._search_long_term(query=effective_query, limit=max(bounded_limit * 2, bounded_limit + 2))
            return self._prioritize_hits(query=normalized_query, hits=long_hits, limit=bounded_limit)

        short_hits = self._search_short_term(query=normalized_query, limit=bounded_limit)
        if len(short_hits) >= bounded_limit:
            return short_hits[:bounded_limit]
        long_hits = self._search_long_term(query=effective_query, limit=max(bounded_limit * 2, bounded_limit + 2))
        prioritized = self._prioritize_hits(query=normalized_query, hits=long_hits, limit=bounded_limit)
        return (short_hits + prioritized)[:bounded_limit]

    def record_task_outcome(self, outcome: TaskOutcome) -> str | None:
        self._session_task_outcomes.append(outcome)
        return self.store_memory(key=f"task_outcome:{outcome.task_id}", value=outcome, scope="long")

    def finalize_session(self, objective: str = "", *, force: bool = False) -> str | None:
        if not self._session_task_outcomes and not force:
            return None

        completed = len(self._session_task_outcomes)
        latest = self._session_task_outcomes[-5:]
        changed: list[str] = []
        verifications: list[str] = []
        for item in latest:
            changed.extend(item.what_changed)
            verifications.extend(item.verification)

        brief = {
            "objective": objective,
            "completed_tasks": completed,
            "key_changes": changed[-10:],
            "recent_verification": verifications[-10:],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.store_memory(key="project_brief:latest", value=brief, scope="long")

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

    def _prioritize_hits(self, query: str, hits: list[dict], limit: int) -> list[dict]:
        if not hits:
            return []
        lowered_query = (query or "").lower()
        epic_tokens = self._extract_epic_tokens(lowered_query)

        def score(hit: dict[str, Any]) -> float:
            category = str(hit.get("category", "")).lower()
            title = str(hit.get("title", "")).lower()
            content = str(hit.get("content", "")).lower()
            keywords = " ".join(hit.get("keywords", []) or []).lower()

            rank = 0.0
            if category == "architecture_decision":
                rank += 5.0
            if category == "project_brief":
                rank += 2.0 if not lowered_query.strip() else 0.2
            if any(token and (token in title or token in content or token in keywords) for token in epic_tokens):
                rank += 4.0
            if lowered_query and lowered_query in f"{title} {content} {keywords}":
                rank += 1.0
            return rank

        ranked = sorted(hits, key=score, reverse=True)
        return ranked[:limit]

    def _extract_epic_tokens(self, lowered_query: str) -> list[str]:
        cleaned = lowered_query.replace(":", " ").replace("#", " ")
        words = [token.strip() for token in cleaned.split() if token.strip()]
        if not words:
            return []
        epic_markers = {"epic", "エピック"}
        if any(marker in words for marker in epic_markers):
            return [w for w in words if w not in epic_markers][:4]
        return words[:3]

    def _to_long_term_entry(self, record: dict[str, Any]) -> dict[str, Any]:
        value = record.get("value")
        content = str(value)
        title = str(record["key"])[:120] or "agent-memory"
        category = "agent_loop"
        keywords = ["agent", "loop", "summary"]

        if isinstance(value, dict):
            type_name = str(value.get("type", "")).lower()
            if type_name in {"architecturedecision", "taskoutcome", "modulemap", "riskregister"}:
                category = self._type_to_category(type_name)
            if value.get("epic"):
                keywords.append(str(value["epic"]))
        elif is_dataclass(value):
            type_name = value.__class__.__name__.lower()
            category = self._type_to_category(type_name)
            epic = getattr(value, "epic", "")
            if epic:
                keywords.append(str(epic))
            if isinstance(value, ModuleMap):
                keywords.append(value.module)

        if str(record.get("key", "")).startswith("project_brief:"):
            category = "project_brief"
            keywords.extend(["project", "brief", "handoff"])

        return {
            "category": category,
            "title": title,
            "content": content,
            "keywords": list(dict.fromkeys(keywords)),
        }

    def _type_to_category(self, type_name: str) -> str:
        if type_name == "architecturedecision":
            return "architecture_decision"
        if type_name == "taskoutcome":
            return "task_outcome"
        if type_name == "modulemap":
            return "module_map"
        if type_name == "riskregister":
            return "risk_register"
        return "agent_loop"

    def _to_serializable(self, value: Any) -> Any:
        if is_dataclass(value):
            payload = asdict(value)
            payload["type"] = value.__class__.__name__
            return payload
        if isinstance(value, list):
            return [self._to_serializable(v) for v in value]
        if isinstance(value, dict):
            return {k: self._to_serializable(v) for k, v in value.items()}
        return value
