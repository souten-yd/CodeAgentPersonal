from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _estimate_tokens(text: str) -> int:
    """
    簡易トークン見積もり。
    厳密トークナイザは導入せず、概算（約4文字=1 token）で扱う。
    """
    return max(1, len(text) // 4)


def _truncate_to_token_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    char_budget = max_tokens * 4
    if len(text) <= char_budget:
        return text
    return text[:char_budget].rstrip() + "…"


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class FileSummaryEntry:
    path: str
    content_hash: str
    summary: str
    estimated_tokens: int
    updated_at: str


class FileSummaryCache:
    """
    ファイルごとの要約キャッシュ。
    - 要約は 200 tokens 以下を保証
    - 内容ハッシュが同一なら既存要約を再利用
    """

    def __init__(self, max_summary_tokens: int = 200) -> None:
        self.max_summary_tokens = max_summary_tokens
        self._cache: dict[str, FileSummaryEntry] = {}

    def get(self, path: str) -> FileSummaryEntry | None:
        return self._cache.get(path)

    def get_or_update(
        self,
        path: str,
        content: str,
        summarizer: Callable[[str], str] | None = None,
    ) -> FileSummaryEntry:
        content_hash = _hash_text(content)
        existing = self._cache.get(path)
        if existing and existing.content_hash == content_hash:
            return existing

        raw_summary = summarizer(content) if summarizer else self._default_summary(content)
        compact_summary = _normalize_whitespace(raw_summary)
        bounded_summary = _truncate_to_token_budget(compact_summary, self.max_summary_tokens)
        entry = FileSummaryEntry(
            path=path,
            content_hash=content_hash,
            summary=bounded_summary,
            estimated_tokens=_estimate_tokens(bounded_summary),
            updated_at=_utcnow_iso(),
        )
        self._cache[path] = entry
        return entry

    def _default_summary(self, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return ""
        return " ".join(lines[:12])


class ToolResultCache:
    """同一ツール・同一引数の結果再利用キャッシュ。"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def _make_key(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        stable_input = json.dumps(tool_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{tool_name}:{stable_input}"

    def get(self, tool_name: str, tool_input: dict[str, Any]) -> Any | None:
        return self._cache.get(self._make_key(tool_name, tool_input))

    def set(self, tool_name: str, tool_input: dict[str, Any], result: Any) -> None:
        self._cache[self._make_key(tool_name, tool_input)] = result

    def get_or_run(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        runner: Callable[[], Any],
    ) -> Any:
        key = self._make_key(tool_name, tool_input)
        if key in self._cache:
            return self._cache[key]
        result = runner()
        self._cache[key] = result
        return result


class ContextBuilder:
    """Planner へ渡すコンテキスト構築インターフェース。"""

    def build(self, objective: str, runtime_state: dict) -> dict:
        raise NotImplementedError


class TaskV2ContextBuilder(ContextBuilder):
    """
    Task v2 向けのコンテキスト構築。
    - 全文 read を直接コンテキストへ貼り付けない
    - 関連するファイル要約のみ注入
    - 必要時はツールによる局所読み込みを前提とする
    """

    def __init__(
        self,
        file_summary_cache: FileSummaryCache | None = None,
        tool_result_cache: ToolResultCache | None = None,
        max_injected_summaries: int = 8,
    ) -> None:
        self.file_summary_cache = file_summary_cache or FileSummaryCache()
        self.tool_result_cache = tool_result_cache or ToolResultCache()
        self.max_injected_summaries = max_injected_summaries

    def build(self, objective: str, runtime_state: dict) -> dict:
        plan_text = str(runtime_state.get("plan", ""))
        current_step = str(runtime_state.get("current_step", ""))
        file_candidates = runtime_state.get("file_candidates", []) or []
        summary_fn = runtime_state.get("summarizer")

        relevant = self._select_relevant_summaries(
            objective=objective,
            plan_text=plan_text,
            current_step=current_step,
            file_candidates=file_candidates,
            summarizer=summary_fn if callable(summary_fn) else None,
        )

        return {
            "objective": objective,
            "plan": plan_text,
            "current_step": current_step,
            "relevant_file_summaries": relevant,
            "policies": {
                "inline_full_reads": "forbidden",
                "read_strategy": "tool_based_local_read_on_demand",
            },
        }

    def _select_relevant_summaries(
        self,
        objective: str,
        plan_text: str,
        current_step: str,
        file_candidates: list[dict[str, Any]],
        summarizer: Callable[[str], str] | None,
    ) -> list[dict[str, Any]]:
        query_terms = self._extract_terms(" ".join([objective, plan_text, current_step]))
        scored: list[tuple[int, FileSummaryEntry]] = []

        for item in file_candidates:
            path = str(item.get("path", "")).strip()
            content = item.get("content")
            if not path or not isinstance(content, str):
                continue
            entry = self.file_summary_cache.get_or_update(path=path, content=content, summarizer=summarizer)
            haystack_terms = self._extract_terms(f"{path} {entry.summary}")
            overlap = len(query_terms & haystack_terms) if query_terms else 0
            scored.append((overlap, entry))

        scored.sort(key=lambda x: (x[0], x[1].updated_at), reverse=True)
        selected = [entry for score, entry in scored if score > 0][: self.max_injected_summaries]
        if not selected:
            selected = [entry for _, entry in scored[: self.max_injected_summaries]]

        return [
            {
                "path": entry.path,
                "summary": entry.summary,
                "content_hash": entry.content_hash,
                "estimated_tokens": entry.estimated_tokens,
            }
            for entry in selected
        ]

    def _extract_terms(self, text: str) -> set[str]:
        normalized = text.lower()
        return {token for token in re.findall(r"[a-z0-9_./-]+", normalized) if len(token) >= 3}
