from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib import parse, request

from app.nexus.config import load_runtime_config
from app.nexus.evidence import EvidenceItem


_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

_SEARCH_MODE_SETTINGS: dict[str, dict[str, int]] = {
    "quick": {"max_queries": 2, "max_results_per_query": 3},
    "standard": {"max_queries": 4, "max_results_per_query": 5},
    "deep": {"max_queries": 6, "max_results_per_query": 8},
    "exhaustive": {"max_queries": 8, "max_results_per_query": 12},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_mode(mode: str | None) -> str:
    raw_mode = (mode or "standard").strip().lower()
    if raw_mode in _SEARCH_MODE_SETTINGS:
        return raw_mode
    return "standard"


def _resolve_depth(mode: str | None, depth: str | None) -> str:
    """depth と mode の両入力を受け取り、最終的な探索深度を返す。"""
    depth_mode = _normalize_mode(depth)
    if depth and depth_mode in _SEARCH_MODE_SETTINGS:
        return depth_mode
    return _normalize_mode(mode)


def _normalize_scope(scope: str | list[str] | None) -> list[str]:
    if scope is None:
        return []
    raw_values = [scope] if isinstance(scope, str) else scope
    normalized: list[str] = []
    for raw in raw_values:
        value = str(raw or "").strip()
        if not value:
            continue
        lower = value.lower()
        if lower not in normalized:
            normalized.append(lower)
    return normalized


def _normalize_language(language: str | None) -> str:
    raw = (language or "en").strip().lower()
    if not raw:
        return "en"
    aliases = {
        "jp": "ja",
        "jpn": "ja",
        "eng": "en",
    }
    return aliases.get(raw, raw)


def _scope_suffix(scope_tokens: list[str]) -> str:
    mapped: list[str] = []
    for token in scope_tokens:
        if token == "news":
            mapped.append("latest news")
        elif token == "official":
            mapped.append("official source")
        elif token.startswith("site:") or token.startswith("filetype:"):
            mapped.append(token)
        else:
            mapped.append(token)
    return " ".join(mapped).strip()


_LANGUAGE_BASE_SEEDS: dict[str, list[str]] = {
    "ja": [
        "{topic}",
        "{topic} 最新",
        "{topic} 分析",
        "{topic} 見通し",
        "{topic} リスク 機会",
        "{topic} 触媒",
        "{topic} バリュエーション",
        "{topic} 専門家 コメント",
    ],
    "en": [
        "{topic}",
        "{topic} latest",
        "{topic} analysis",
        "{topic} outlook",
        "{topic} risks opportunities",
        "{topic} catalysts",
        "{topic} valuation",
        "{topic} expert commentary",
    ],
}


_SCOPE_EXTRA_SEEDS: dict[str, dict[str, list[str]]] = {
    "news": {
        "ja": ["{topic} 速報", "{topic} ヘッドライン", "{topic} 今日"],
        "en": ["{topic} breaking news", "{topic} headlines", "{topic} today"],
    },
    "official": {
        "ja": ["{topic} 公式 発表", "{topic} IR", "{topic} プレスリリース"],
        "en": ["{topic} official statement", "{topic} investor relations", "{topic} press release"],
    },
    "academic": {
        "ja": ["{topic} 論文", "{topic} 研究", "{topic} 学術"],
        "en": ["{topic} research paper", "{topic} study", "{topic} academic"],
    },
}


def _build_query_seeds(topic: str, *, language: str, scope_tokens: list[str]) -> list[str]:
    lang_key = "ja" if language == "ja" else "en"
    templates = _LANGUAGE_BASE_SEEDS[lang_key]
    seeds = [template.format(topic=topic) for template in templates]
    for scope_token in scope_tokens:
        scoped_templates = (_SCOPE_EXTRA_SEEDS.get(scope_token) or {}).get(lang_key, [])
        seeds.extend(template.format(topic=topic) for template in scoped_templates)
    return seeds


def plan_web_queries(
    topic: str,
    *,
    mode: str = "standard",
    depth: str | None = None,
    max_queries: int | None = None,
    scope: str | list[str] | None = None,
    language: str | None = None,
) -> list[str]:
    """Build lightweight web-search queries from one topic string."""
    topic = (topic or "").strip()
    if not topic:
        return []

    normalized_mode = _resolve_depth(mode, depth)
    normalized_scope = _normalize_scope(scope)
    normalized_language = _normalize_language(language)
    suffix = _scope_suffix(normalized_scope)
    default_max_queries = _SEARCH_MODE_SETTINGS[normalized_mode]["max_queries"]
    query_cap = max(1, max_queries if max_queries is not None else default_max_queries)

    seeds = _build_query_seeds(topic, language=normalized_language, scope_tokens=normalized_scope)

    unique: list[str] = []
    for seed in seeds:
        query = seed
        if suffix:
            query = f"{query} {suffix}"
        q = " ".join(query.split())
        if q and q not in unique:
            unique.append(q)
        if len(unique) >= query_cap:
            break
    return unique


def _build_stub_items(queries: list[str], *, reason: str) -> list[dict[str, Any]]:
    return [
        {
            "query": query,
            "rank": 1,
            "title": f"[stub] {query}",
            "url": "",
            "snippet": reason,
            "age": None,
            "is_stub": True,
        }
        for query in queries
    ]


def run_web_search(
    queries: list[str],
    *,
    mode: str = "standard",
    depth: str | None = None,
    max_results_per_query: int | None = None,
    scope: str | list[str] | None = None,
    language: str | None = None,
    country: str = "US",
    search_lang: str | None = None,
) -> dict[str, Any]:
    """Run configured web search provider and return a non-fatal normalized payload."""
    cfg = load_runtime_config()
    normalized_mode = _resolve_depth(mode, depth)
    mode_defaults = _SEARCH_MODE_SETTINGS[normalized_mode]
    result_cap = max_results_per_query if max_results_per_query is not None else mode_defaults["max_results_per_query"]
    result_cap = max(1, min(20, int(result_cap)))
    normalized_scope = _normalize_scope(scope)
    normalized_language = _normalize_language(language)
    effective_search_lang = _normalize_language(search_lang) if search_lang else normalized_language

    normalized_queries = [q.strip() for q in queries if (q or "").strip()]
    effective_query_plan = {
        "requested_scope": scope,
        "normalized_scope": normalized_scope,
        "requested_language": language,
        "requested_depth": depth if depth is not None else mode,
        "resolved_depth": normalized_mode,
        "search_lang": effective_search_lang,
        "queries": normalized_queries,
        "generated_queries": normalized_queries,
    }

    if not normalized_queries:
        return {
            "provider": cfg.web_search_provider,
            "mode": normalized_mode,
            "configured": bool(cfg.brave_search_api_key),
            "effective_query_plan": effective_query_plan,
            "generated_queries": normalized_queries,
            "items": [],
            "message": "query が空です。",
        }

    if not cfg.enable_web:
        message = "NEXUS_ENABLE_WEB=false のため、Web検索は無効です。"
        return {
            "provider": cfg.web_search_provider,
            "mode": normalized_mode,
            "configured": False,
            "effective_query_plan": effective_query_plan,
            "generated_queries": normalized_queries,
            "items": _build_stub_items(normalized_queries, reason=message),
            "message": message,
            "non_fatal": True,
        }

    if cfg.web_search_provider != "brave":
        message = (
            "未対応プロバイダです。NEXUS_WEB_SEARCH_PROVIDER=brave を設定してください。"
        )
        return {
            "provider": cfg.web_search_provider,
            "mode": normalized_mode,
            "configured": False,
            "effective_query_plan": effective_query_plan,
            "generated_queries": normalized_queries,
            "items": _build_stub_items(normalized_queries, reason=message),
            "message": message,
            "non_fatal": True,
        }

    if not cfg.brave_search_api_key:
        message = "設定不足: BRAVE_SEARCH_API_KEY が未設定のため、Web検索はスタブ結果を返します。"
        return {
            "provider": "brave",
            "mode": normalized_mode,
            "configured": False,
            "effective_query_plan": effective_query_plan,
            "generated_queries": normalized_queries,
            "message": message,
            "non_fatal": True,
            "items": _build_stub_items(
                normalized_queries,
                reason="BRAVE_SEARCH_API_KEY を設定すると実検索結果に切り替わります。",
            ),
        }

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for query in normalized_queries:
        params = parse.urlencode(
            {
                "q": query,
                "count": result_cap,
                "country": country,
                "search_lang": effective_search_lang,
            }
        )
        req = request.Request(
            f"{_BRAVE_ENDPOINT}?{params}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": cfg.brave_search_api_key,
            },
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query}: {exc}")
            continue

        web_results = (payload.get("web") or {}).get("results") or []
        for idx, entry in enumerate(web_results, start=1):
            items.append(
                {
                    "query": query,
                    "rank": idx,
                    "title": entry.get("title") or "",
                    "url": entry.get("url") or "",
                    "snippet": entry.get("description") or "",
                    "age": entry.get("age"),
                    "is_stub": False,
                }
            )

    response: dict[str, Any] = {
        "provider": "brave",
        "mode": normalized_mode,
        "configured": True,
        "effective_query_plan": effective_query_plan,
        "generated_queries": normalized_queries,
        "items": items,
        "message": "ok",
    }
    if errors:
        response["errors"] = errors
    return response


def normalize_search_rows(search_output: dict[str, Any]) -> list[dict[str, Any]]:
    """Provider依存の検索結果を Evidence 生成向け共通形式に揃える。"""
    normalized: list[dict[str, Any]] = []
    provider = str(search_output.get("provider") or "unknown")

    for idx, row in enumerate(search_output.get("items") or [], start=1):
        query = str(row.get("query") or "")
        rank = int(row.get("rank") or idx)
        normalized.append(
            {
                "provider": provider,
                "query": query,
                "rank": rank,
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or "about:blank"),
                "snippet": str(row.get("snippet") or ""),
                "age": row.get("age"),
                "is_stub": bool(row.get("is_stub")),
            }
        )
    return normalized


def build_web_evidence(search_output: dict[str, Any], *, note: str | None = None) -> list[EvidenceItem]:
    """Normalize web-search output to persistable EvidenceItem list."""
    retrieved_at = _now_iso()
    items: list[EvidenceItem] = []

    for idx, row in enumerate(normalize_search_rows(search_output), start=1):
        query = row["query"]
        rank = row["rank"]
        chunk_id = f"web:{query}:{rank}:{idx}"
        citation_label = f"[web-{idx}]"

        items.append(
            EvidenceItem(
                source_type="web",
                document_id="",
                chunk_id=chunk_id,
                url=row["url"],
                retrieved_at=retrieved_at,
                title=row["title"],
                citation_label=citation_label,
                note=note or "web_search",
                quote=row["snippet"],
                metadata_json={
                    "provider": row["provider"],
                    "query": query,
                    "rank": rank,
                    "title": row["title"],
                    "age": row["age"],
                    "is_stub": row["is_stub"],
                    "mode": search_output.get("mode", "standard"),
                },
            )
        )
    return items
