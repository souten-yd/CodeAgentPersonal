from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib import error as urllib_error
from urllib import parse, request

from app.nexus.config import load_runtime_config
from app.nexus.evidence import EvidenceItem


_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_SEARXNG_ENDPOINT_PATH = "/search"
_QUOTA_ERROR_KEYWORDS = ("quota", "billing", "payment", "plan", "subscription", "rate limit")
_TEMPORARILY_DISABLED_PROVIDERS: dict[str, float] = {}

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
            "provider": "stub",
            "query": query,
            "rank": 1,
            "title": f"[stub] {query}",
            "url": "",
            "snippet": reason,
            "age": None,
            "engine": "stub",
            "is_stub": True,
        }
        for query in queries
    ]


def _normalize_provider_result(
    *,
    provider: str,
    query: str,
    rank: int,
    title: str | None,
    url: str | None,
    snippet: str | None,
    age: str | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "query": query,
        "rank": rank,
        "title": title or "",
        "url": url or "",
        "snippet": snippet or "",
        "age": age,
        "engine": engine,
        "is_stub": False,
    }


def _is_paid_or_quota_error(
    *,
    status_code: int | None = None,
    body: str | None = None,
    error_message: str | None = None,
) -> bool:
    normalized_body = (body or "").lower()
    normalized_error = (error_message or "").lower()
    if status_code in {402, 429}:
        return True
    if status_code == 403 and any(keyword in normalized_body or keyword in normalized_error for keyword in _QUOTA_ERROR_KEYWORDS):
        return True
    return any(keyword in normalized_body or keyword in normalized_error for keyword in _QUOTA_ERROR_KEYWORDS)


def _mark_provider_temporarily_disabled(provider: str, *, cooldown_sec: int, reason: str | None = None) -> None:
    _ = reason
    until_timestamp = datetime.now(timezone.utc).timestamp() + max(60, cooldown_sec)
    _TEMPORARILY_DISABLED_PROVIDERS[provider] = until_timestamp


def _should_skip_provider(provider: str, cfg: Any) -> bool:
    if provider == "brave" and cfg.search_free_only and not cfg.search_paid_providers_enabled:
        return True
    disabled_until = _TEMPORARILY_DISABLED_PROVIDERS.get(provider)
    if disabled_until is None:
        return False
    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts < disabled_until:
        return True
    _TEMPORARILY_DISABLED_PROVIDERS.pop(provider, None)
    return False


def _run_searxng_search(
    *,
    cfg: Any,
    queries: list[str],
    result_cap: int,
    search_lang: str,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    base_url = cfg.searxng_url.rstrip("/")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    had_connection_failure = False

    for query in queries:
        params = parse.urlencode(
            {
                "q": query,
                "format": "json",
                "language": search_lang,
                "categories": "general",
            }
        )
        req = request.Request(f"{base_url}{_SEARXNG_ENDPOINT_PATH}?{params}", headers={"Accept": "application/json"}, method="GET")
        try:
            with request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            had_connection_failure = True
            errors.append(f"{query}: {exc}")
            continue

        results = payload.get("results") or []
        for idx, entry in enumerate(results[:result_cap], start=1):
            items.append(
                _normalize_provider_result(
                    provider="searxng",
                    query=query,
                    rank=idx,
                    title=entry.get("title"),
                    url=entry.get("url"),
                    snippet=entry.get("content"),
                    age=entry.get("publishedDate"),
                    engine=entry.get("engine"),
                )
            )
    return items, errors, had_connection_failure


def _run_brave_search(
    *,
    cfg: Any,
    queries: list[str],
    result_cap: int,
    country: str,
    search_lang: str,
) -> tuple[list[dict[str, Any]], list[str], bool, bool]:
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    had_connection_failure = False
    should_cooldown = False

    for query in queries:
        params = parse.urlencode(
            {
                "q": query,
                "count": result_cap,
                "country": country,
                "search_lang": search_lang,
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
                body = resp.read().decode("utf-8")
                payload = json.loads(body)
                if _is_paid_or_quota_error(status_code=getattr(resp, "status", None), body=body):
                    should_cooldown = True
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            is_quota = _is_paid_or_quota_error(status_code=exc.code, body=body, error_message=str(exc))
            if is_quota:
                should_cooldown = True
            errors.append(f"{query}: HTTP {exc.code} {exc.reason}")
            continue
        except Exception as exc:  # noqa: BLE001
            had_connection_failure = True
            if _is_paid_or_quota_error(error_message=str(exc)):
                should_cooldown = True
            errors.append(f"{query}: {exc}")
            continue

        web_results = (payload.get("web") or {}).get("results") or []
        for idx, entry in enumerate(web_results, start=1):
            items.append(
                _normalize_provider_result(
                    provider="brave",
                    query=query,
                    rank=idx,
                    title=entry.get("title"),
                    url=entry.get("url"),
                    snippet=entry.get("description"),
                    age=entry.get("age"),
                    engine="brave",
                )
            )
    return items, errors, had_connection_failure, should_cooldown


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

    configured_by_provider: dict[str, bool] = {}

    if not normalized_queries:
        selected_provider = (cfg.web_search_provider or "").strip().lower() or "unknown"
        return {
            "provider": selected_provider,
            "selected_provider": selected_provider,
            "attempted_providers": [],
            "fallback_used": False,
            "skipped_providers": {},
            "provider_errors": {},
            "mode": normalized_mode,
            "configured": bool(cfg.brave_search_api_key),
            "non_fatal": True,
            "effective_query_plan": effective_query_plan,
            "generated_queries": normalized_queries,
            "items": [],
            "total_items": 0,
            "message": "query が空です。",
        }

    if not cfg.enable_web:
        message = "NEXUS_ENABLE_WEB=false のため、Web検索は無効です。"
        return {
            "provider": cfg.web_search_provider,
            "selected_provider": (cfg.web_search_provider or "").strip().lower() or "unknown",
            "attempted_providers": [],
            "fallback_used": False,
            "skipped_providers": {},
            "provider_errors": {},
            "mode": normalized_mode,
            "configured": False,
            "effective_query_plan": effective_query_plan,
            "generated_queries": normalized_queries,
            "items": _build_stub_items(normalized_queries, reason=message),
            "total_items": len(normalized_queries),
            "message": message,
            "non_fatal": True,
        }

    ordered_providers: list[str] = []
    for provider in [cfg.web_search_provider, *cfg.search_fallback_providers]:
        candidate = (provider or "").strip().lower()
        if candidate and candidate not in ordered_providers:
            ordered_providers.append(candidate)

    provider_errors: dict[str, list[str]] = {}
    attempted_providers: list[str] = []
    skip_reasons: dict[str, str] = {}

    for provider in ordered_providers:
        if _should_skip_provider(provider, cfg):
            skip_reasons[provider] = "cooldown もしくは free-only 設定によりスキップされました。"
            configured_by_provider[provider] = provider != "brave" or bool(cfg.brave_search_api_key)
            continue

        if provider == "brave" and not cfg.brave_search_api_key:
            provider_errors.setdefault(provider, []).append("BRAVE_SEARCH_API_KEY が未設定です。")
            configured_by_provider[provider] = False
            continue

        configured_by_provider[provider] = True
        attempted_providers.append(provider)
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        had_connection_failure = False
        should_cooldown = False

        if provider == "searxng":
            items, errors, had_connection_failure = _run_searxng_search(
                cfg=cfg,
                queries=normalized_queries,
                result_cap=result_cap,
                search_lang=effective_search_lang,
            )
        elif provider == "brave":
            items, errors, had_connection_failure, should_cooldown = _run_brave_search(
                cfg=cfg,
                queries=normalized_queries,
                result_cap=result_cap,
                country=country,
                search_lang=effective_search_lang,
            )
        else:
            provider_errors.setdefault(provider, []).append("未対応プロバイダです。")
            continue

        if should_cooldown:
            _mark_provider_temporarily_disabled(
                provider,
                cooldown_sec=cfg.search_provider_cooldown_sec,
                reason="quota / billing",
            )

        if items:
            selected_provider = provider
            primary_provider = ordered_providers[0] if ordered_providers else selected_provider
            response: dict[str, Any] = {
                "provider": primary_provider,
                "selected_provider": selected_provider,
                "attempted_providers": attempted_providers,
                "fallback_used": selected_provider != primary_provider,
                "skipped_providers": skip_reasons,
                "provider_errors": provider_errors,
                "mode": normalized_mode,
                "configured": configured_by_provider.get(selected_provider, True),
                "non_fatal": False,
                "effective_query_plan": effective_query_plan,
                "generated_queries": normalized_queries,
                "items": items,
                "total_items": len(items),
                "message": "ok",
            }
            if errors:
                response["errors"] = errors
            return response

        provider_errors[provider] = errors or ["結果が空のため、次の provider にフォールバックしました。"]
        if not had_connection_failure and not errors:
            provider_errors[provider].append("空結果フォールバック")

    message = "すべての検索 provider が失敗したため、non-fatal stub を返します。"
    selected_provider = attempted_providers[-1] if attempted_providers else (ordered_providers[0] if ordered_providers else cfg.web_search_provider)
    primary_provider = ordered_providers[0] if ordered_providers else cfg.web_search_provider
    stub_items = _build_stub_items(normalized_queries, reason=message)
    return {
        "provider": primary_provider,
        "selected_provider": selected_provider,
        "attempted_providers": attempted_providers,
        "fallback_used": bool(attempted_providers and selected_provider != primary_provider),
        "mode": normalized_mode,
        "configured": configured_by_provider.get(selected_provider, False),
        "effective_query_plan": effective_query_plan,
        "generated_queries": normalized_queries,
        "items": stub_items,
        "total_items": len(stub_items),
        "message": message,
        "non_fatal": True,
        "provider_errors": provider_errors,
        "skipped_providers": skip_reasons,
    }


def normalize_search_rows(search_output: dict[str, Any]) -> list[dict[str, Any]]:
    """Provider依存の検索結果を Evidence 生成向け共通形式に揃える。"""
    normalized: list[dict[str, Any]] = []
    for idx, row in enumerate(search_output.get("items") or [], start=1):
        provider = str(row.get("provider") or search_output.get("provider") or "unknown")
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
                "engine": row.get("engine"),
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
                    "engine": row["engine"],
                    "is_stub": row["is_stub"],
                    "mode": search_output.get("mode", "standard"),
                },
            )
        )
    return items
