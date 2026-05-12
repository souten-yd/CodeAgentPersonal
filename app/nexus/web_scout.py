from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib import error as urllib_error
from urllib import parse, request

from app.nexus.config import load_runtime_config
from app.nexus.evidence import EvidenceItem


_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_SEARXNG_ENDPOINT_PATH = "/search"
_SEARXNG_DEGRADED_ERROR_CATEGORY = "searxng_engine_captcha_or_non_json"
_SEARXNG_DEGRADED_HINT = "Disable CAPTCHA-prone engines or use safe_research profile"
_SEARXNG_DEGRADED_KEYWORDS = ("captcha", "jsondecodeerror", "json decode", "non-json", "non json", "extra data", "duckduckgo", "startpage", "google", "brave", "karmasearch", "too many", "403")
_QUOTA_ERROR_KEYWORDS = ("quota", "billing", "payment", "plan", "subscription", "rate limit")
_TEMPORARILY_DISABLED_PROVIDERS: dict[str, float] = {}
_LAST_WEB_SEARCH_STATUS: dict[str, Any] = {
    "last_provider_errors": {},
    "last_selected_provider": None,
    "last_non_fatal": None,
    "last_message": "",
    "last_diagnostics": [],
    "last_search_at": None,
}


_NOISY_SEARXNG_ENGINES = {"duckduckgo", "startpage", "google", "bing", "brave", "karmasearch", "yahoo", "qwant", "mojeek"}
_BROAD_WEB_ENGINES = ("google", "bing", "brave", "duckduckgo")
_EXPERIMENTAL_WEB_ENGINES = ("mojeek",)
_SAFE_FALLBACK_ENGINES = ("wikipedia", "wikidata", "arxiv", "crossref", "openalex", "github")
_PROFILE_SEARXNG_DEFAULTS: dict[str, str] = {
    "general": "wikipedia,wikidata,github,stackoverflow",
    "web": "wikipedia,wikidata,github,stackoverflow",
    "academic": "arxiv,crossref,openalex,semantic scholar,wikipedia",
    "official": "wikidata,wikipedia,github",
    "source": "wikipedia,wikidata,arxiv,crossref,openalex,github",
    "news": "wikipedia,wikidata",
    "market": "wikipedia,wikidata,github",
    "technical": "arxiv,crossref,openalex,semantic scholar,wikipedia,github",
}
_BROAD_PROFILE_SEARXNG_DEFAULTS: dict[str, str] = {
    "general": "google,bing,brave,duckduckgo,wikipedia,wikidata,github,stackoverflow",
    "web": "google,bing,brave,duckduckgo,wikipedia,wikidata,github,stackoverflow",
    "academic": "arxiv,crossref,openalex,semantic scholar,wikipedia",
    "official": "google,bing,brave,duckduckgo,wikidata,wikipedia,github",
    "source": "google,bing,brave,duckduckgo,wikipedia,wikidata,arxiv,crossref,openalex,github",
    "news": "google,bing,brave,duckduckgo,wikipedia,wikidata",
    "market": "google,bing,brave,duckduckgo,wikipedia,wikidata,github",
    "technical": "arxiv,crossref,openalex,semantic scholar,wikipedia,github",
}
_PROFILE_ENGINE_ENV: dict[str, str] = {
    "general": "NEXUS_SEARXNG_ENGINES_GENERAL",
    "web": "NEXUS_SEARXNG_ENGINES_GENERAL",
    "news": "NEXUS_SEARXNG_ENGINES_NEWS",
    "market": "NEXUS_SEARXNG_ENGINES_MARKET",
    "official": "NEXUS_SEARXNG_ENGINES_OFFICIAL",
    "academic": "NEXUS_SEARXNG_ENGINES_ACADEMIC",
    "technical": "NEXUS_SEARXNG_ENGINES_ACADEMIC",
    "source": "NEXUS_SEARXNG_ENGINES_SOURCE",
}

_SEARCH_MODE_SETTINGS: dict[str, dict[str, int]] = {
    "quick": {"max_queries": 2, "max_results_per_query": 3},
    "standard": {"max_queries": 4, "max_results_per_query": 5},
    "deep": {"max_queries": 6, "max_results_per_query": 8},
    "exhaustive": {"max_queries": 8, "max_results_per_query": 12},
}


def _split_engine_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _allow_broad_web_engines() -> bool:
    return os.getenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true").strip().lower() in {"1", "true", "yes", "on"}


def _experimental_web_engines() -> list[str]:
    experimental = _split_engine_csv(os.getenv("NEXUS_EXPERIMENTAL_WEB_ENGINES", ",".join(_EXPERIMENTAL_WEB_ENGINES)))
    if os.getenv("NEXUS_ENABLE_YAHOO_SEARCH", "").strip().lower() in {"1", "true", "yes", "on"} and "yahoo" not in [e.lower() for e in experimental]:
        experimental.append("yahoo")
    return _dedupe_engines(experimental, allow_noisy=True)


class EngineHealthTracker:
    """Job-local circuit breaker for CAPTCHA/rate-limit-prone broad SearXNG engines."""

    def __init__(self, broad_engines: list[str] | None = None, safe_fallback_engines: list[str] | None = None) -> None:
        self.broad_engines = _dedupe_engines(broad_engines or _split_engine_csv(os.getenv("NEXUS_BROAD_WEB_ENGINES", ",".join(_BROAD_WEB_ENGINES))), allow_noisy=True)
        self.experimental_engines = _experimental_web_engines()
        self.track_engines = {e.lower() for e in [*self.broad_engines, *self.experimental_engines]}
        self.safe_fallback_engines = _dedupe_engines(safe_fallback_engines or list(_SAFE_FALLBACK_ENGINES), allow_noisy=True)
        self.failures: dict[str, dict[str, Any]] = {}

    def is_suspended(self, engine: str) -> bool:
        state = self.failures.get(str(engine or "").lower()) or {}
        return bool(state.get("suspended_until"))

    def filter_engines(self, engines: list[str]) -> tuple[list[str], bool]:
        filtered = [engine for engine in engines if not self.is_suspended(engine)]
        requested_broad = [engine for engine in engines if engine.lower() in {b.lower() for b in self.broad_engines}]
        active_broad = [engine for engine in requested_broad if not self.is_suspended(engine)]
        fallback = bool(requested_broad and not active_broad)
        if fallback:
            safe = [engine for engine in engines if engine.lower() not in {b.lower() for b in self.broad_engines}]
            filtered = _dedupe_engines([*safe, *self.safe_fallback_engines], allow_noisy=False)
        return filtered, fallback

    def record_error(self, engine: str | None, message: str) -> None:
        if not engine:
            return
        key = str(engine).strip().lower()
        if not key:
            return
        state = self.failures.setdefault(key, {"engine_name": key, "failures": 0, "last_error": "", "suspended_until": None, "captcha_count": 0, "http_403_count": 0, "http_429_count": 0, "timeout_count": 0, "parse_error_count": 0})
        normalized = str(message or "").lower()
        state["failures"] = int(state.get("failures") or 0) + 1
        state["last_error"] = str(message or "")[:500]
        suspend = False
        if "captcha" in normalized or "access denied" in normalized or "too many requests" in normalized:
            state["captcha_count"] = int(state.get("captcha_count") or 0) + (1 if "captcha" in normalized else 0)
            suspend = True
        if "403" in normalized:
            state["http_403_count"] = int(state.get("http_403_count") or 0) + 1
            suspend = True
        if "429" in normalized or "too many requests" in normalized:
            state["http_429_count"] = int(state.get("http_429_count") or 0) + 1
            suspend = True
        if "timeout" in normalized or "timed out" in normalized:
            state["timeout_count"] = int(state.get("timeout_count") or 0) + 1
            suspend = int(state.get("timeout_count") or 0) >= 2
        if "jsondecodeerror" in normalized or "non-json" in normalized or "non json" in normalized:
            state["parse_error_count"] = int(state.get("parse_error_count") or 0) + 1
            suspend = int(state.get("parse_error_count") or 0) >= 2
        if key not in self.track_engines:
            suspend = False
        if suspend:
            state["suspended_until"] = "job_end"

    def record_payload_errors(self, payload_errors: Any) -> None:
        text = str(payload_errors or "")
        for engine in [*self.broad_engines, *self.experimental_engines]:
            if engine.lower() in text.lower():
                self.record_error(engine, text)

    def summary(self) -> dict[str, Any]:
        return {
            "broad_web_enabled": _allow_broad_web_engines(),
            "broad_web_engines": list(self.broad_engines),
            "experimental_web_engines": list(self.experimental_engines),
            "disabled_engines": _split_engine_csv(os.getenv("SEARXNG_DISABLED_ENGINES", "")),
            "suspended_engines": [engine for engine in self.broad_engines if self.is_suspended(engine)],
            "engine_failures": {k: dict(v) for k, v in self.failures.items()},
            "fallback_to_safe_engines": bool(self.broad_engines and all(self.is_suspended(engine) for engine in self.broad_engines)),
        }


def _allow_broad_unsafe_search() -> bool:
    return os.getenv("NEXUS_ALLOW_BROAD_UNSAFE_SEARCH", "").strip().lower() in {"1", "true", "yes", "on"}


def _dedupe_engines(engines: list[str], *, allow_noisy: bool = False) -> list[str]:
    unique: list[str] = []
    for engine in engines:
        normalized = str(engine or "").strip()
        if not normalized:
            continue
        if not allow_noisy and normalized.lower() in _NOISY_SEARXNG_ENGINES:
            continue
        if normalized.lower() not in [item.lower() for item in unique]:
            unique.append(normalized)
    return unique


def _resolve_searxng_engines_param() -> str:
    """Resolve the legacy SearXNG engine allow-list without source-profile context."""
    explicit = os.getenv("NEXUS_SEARXNG_ENGINES", "").strip()
    if explicit:
        return ",".join(_dedupe_engines(_split_engine_csv(explicit), allow_noisy=_allow_broad_unsafe_search()))
    profile = os.getenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research").strip().lower()
    if profile == "broad_unsafe" and _allow_broad_unsafe_search():
        return ""
    return ",".join(
        _dedupe_engines(
            _split_engine_csv(
                os.getenv(
                    "SEARXNG_SAFE_KEEP_ONLY_ENGINES",
                    "wikipedia,wikidata,arxiv,crossref,openalex,semantic scholar,github,stackoverflow",
                )
            )
        )
    )


def resolve_searxng_engines_for_profile(source_profile: str | None, depth: str | None = None, freshness: str | None = None) -> dict[str, Any]:
    """Return source-profile aware SearXNG engine priority and request parameter."""
    profile = str(source_profile or "general").strip().lower() or "general"
    if profile == "web":
        profile = "general"
    if profile not in _PROFILE_SEARXNG_DEFAULTS:
        profile = "general"
    engine_profile = os.getenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research").strip().lower()
    if engine_profile == "broad_unsafe" and _allow_broad_unsafe_search():
        return {
            "source_profile": profile,
            "engine_priority": "broad_unsafe",
            "searxng_engines": [],
            "searxng_engines_param": "",
            "freshness_policy": _freshness_policy_for_profile(profile, freshness),
            "depth": depth or "standard",
        }

    env_name = _PROFILE_ENGINE_ENV.get(profile, "NEXUS_SEARXNG_ENGINES_GENERAL")
    configured = os.getenv(env_name, "").strip()
    broad_enabled = _allow_broad_web_engines() and engine_profile in {"adaptive_broad_research", "broad_research", "broad", ""}
    defaults = _BROAD_PROFILE_SEARXNG_DEFAULTS if broad_enabled else _PROFILE_SEARXNG_DEFAULTS
    engines = _split_engine_csv(configured or defaults[profile])
    if not configured and os.getenv("NEXUS_SEARXNG_ENGINES", "").strip():
        engines = _split_engine_csv(_resolve_searxng_engines_param())
    engines = _dedupe_engines(engines, allow_noisy=broad_enabled)
    return {
        "source_profile": profile,
        "engine_priority": "profile_broad" if broad_enabled and any(e.lower() in _BROAD_WEB_ENGINES for e in engines) else "profile_safe",
        "broad_web_enabled": broad_enabled,
        "broad_web_engines": [e for e in engines if e.lower() in _BROAD_WEB_ENGINES],
        "searxng_engines": engines,
        "searxng_engines_param": ",".join(engines),
        "freshness_policy": _freshness_policy_for_profile(profile, freshness),
        "depth": depth or "standard",
    }



def choose_replacement_engines(
    source_profile: str,
    failed_engine: str | None,
    suspended_engines: set[str],
) -> list[str]:
    """Choose alternate engines for a replenishment retry within one research job."""
    profile = str(source_profile or "general").strip().lower()
    suspended = {str(engine or "").strip().lower() for engine in (suspended_engines or set()) if str(engine or "").strip()}
    failed = str(failed_engine or "").strip().lower()
    if failed:
        suspended.add(failed)
    primary = ["google", "bing", "brave", "duckduckgo"]
    active_primary = [engine for engine in primary if engine not in suspended]
    if active_primary:
        return active_primary
    experimental = [engine for engine in _experimental_web_engines() if engine not in suspended]
    if experimental:
        return experimental
    safe = ["wikipedia", "wikidata", "github"]
    if profile in {"source", "academic", "technical"}:
        safe.extend(["arxiv", "crossref", "openalex"])
    return [engine for engine in _dedupe_engines(safe, allow_noisy=True) if engine.lower() not in suspended]

def _freshness_policy_for_profile(profile: str, freshness: str | None = None) -> str:
    requested = str(freshness or "").strip().lower()
    if requested in {"latest", "recent", "current_year", "last_12_months"}:
        return "prioritize_last_12_months"
    if profile in {"news", "market"}:
        return "prioritize_recent_and_penalize_older_than_2_years"
    if profile in {"official", "academic"}:
        return "balanced_no_harsh_stale_penalty"
    if profile == "source":
        return "prefer_reports_with_moderate_freshness"
    return "balanced"


def get_searxng_engine_status() -> dict[str, Any]:
    general = resolve_searxng_engines_for_profile("general", "standard", "balanced")
    news = resolve_searxng_engines_for_profile("news", "standard", "recent")
    market = resolve_searxng_engines_for_profile("market", "standard", "recent")
    source = resolve_searxng_engines_for_profile("source", "standard", "balanced")
    academic = resolve_searxng_engines_for_profile("academic", "standard", "balanced")
    disabled_engines = _split_engine_csv(os.getenv("SEARXNG_DISABLED_ENGINES", ""))
    disabled_broad = {e.lower() for e in disabled_engines} & {"google", "bing", "brave", "duckduckgo", "mojeek"}
    warning = ""
    if os.getenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research").strip().lower() == "safe_research":
        warning = "SearXNG is running in safe_research; broad web engines are disabled."
    elif disabled_broad:
        warning = "Broad or experimental engines are disabled by environment."
    elif not _allow_broad_web_engines():
        warning = "NEXUS_ALLOW_BROAD_WEB_ENGINES is false."
    return {
        "searxng_engine_profile": os.getenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research"),
        "broad_web_enabled": _allow_broad_web_engines(),
        "broad_web_engines": _split_engine_csv(os.getenv("NEXUS_BROAD_WEB_ENGINES", ",".join(_BROAD_WEB_ENGINES))),
        "experimental_web_engines": _experimental_web_engines(),
        "disabled_engines": disabled_engines,
        "effective_engines_general": general.get("searxng_engines", []),
        "effective_engines_news": news.get("searxng_engines", []),
        "effective_engines_market": market.get("searxng_engines", []),
        "effective_engines_source": source.get("searxng_engines", []),
        "effective_engines_academic": academic.get("searxng_engines", []),
        "startup_contract_warning": warning,
        "searxng_health_engine": os.getenv("SEARXNG_HEALTH_ENGINE", "wikipedia"),
        "source_profile": general.get("source_profile"),
        "engine_priority": general.get("engine_priority"),
        "freshness_policy": general.get("freshness_policy"),
    }

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_last_web_search_status(search_output: dict[str, Any]) -> None:
    _LAST_WEB_SEARCH_STATUS.update(
        {
            "last_provider_errors": dict(search_output.get("provider_errors") or {}),
            "last_selected_provider": search_output.get("selected_provider"),
            "last_non_fatal": bool(search_output.get("non_fatal", False)),
            "last_message": str(search_output.get("message") or ""),
            "last_diagnostics": list(search_output.get("diagnostics") or []),
            "last_search_at": _now_iso(),
        }
    )


def get_last_web_search_status() -> dict[str, Any]:
    return dict(_LAST_WEB_SEARCH_STATUS)


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
        "ja": ["{topic} 最新", "{topic} 今日", "{topic} 速報", "{topic} news", "{topic} latest", "{topic} press release"],
        "en": ["{topic} latest", "{topic} today", "{topic} breaking news", "{topic} news", "{topic} press release"],
    },
    "market": {
        "ja": ["{topic} 市場規模 CAGR 予測", "{topic} 主要企業 投資", "{topic} partnership market outlook"],
        "en": ["{topic} market size CAGR forecast", "{topic} key companies investment", "{topic} partnership market outlook"],
    },
    "official": {
        "ja": ["{topic} 公式 官公庁 白書 報告書", "{topic} site:go.jp", "{topic} site:.gov", "{topic} PDF"],
        "en": ["{topic} official government white paper report", "{topic} site:.gov", "{topic} site:go.jp", "{topic} PDF"],
    },
    "source": {
        "ja": ["{topic} PDF report", "{topic} white paper", "{topic} annual report", "{topic} investor relations"],
        "en": ["{topic} PDF report", "{topic} white paper", "{topic} annual report", "{topic} investor relations"],
    },
    "academic": {
        "ja": ["{topic} paper arxiv", "{topic} study review", "{topic} IEEE", "{topic} 論文 研究"],
        "en": ["{topic} paper arxiv", "{topic} study review", "{topic} IEEE", "{topic} research paper"],
    },
}


def _build_query_seeds(topic: str, *, language: str, scope_tokens: list[str], source_profile: str | None = None) -> list[str]:
    lang_key = "ja" if language == "ja" else "en"
    templates = _LANGUAGE_BASE_SEEDS[lang_key]
    seeds = [template.format(topic=topic) for template in templates]
    profile_tokens = _normalize_scope(source_profile)
    for scope_token in [*profile_tokens, *scope_tokens]:
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
    source_profile: str | None = None,
) -> list[str]:
    """Build lightweight web-search queries from one topic string."""
    topic = (topic or "").strip()
    if not topic:
        return []

    normalized_mode = _resolve_depth(mode, depth)
    normalized_scope = _normalize_scope(scope)
    if source_profile is None and len(normalized_scope) == 1 and normalized_scope[0] in _PROFILE_SEARXNG_DEFAULTS:
        source_profile = normalized_scope[0]
    normalized_language = _normalize_language(language)
    suffix = _scope_suffix(normalized_scope)
    default_max_queries = _SEARCH_MODE_SETTINGS[normalized_mode]["max_queries"]
    query_cap = max(1, max_queries if max_queries is not None else default_max_queries)

    seeds = _build_query_seeds(topic, language=normalized_language, scope_tokens=normalized_scope, source_profile=source_profile)

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
    if provider in {"brave", "braveapi", "brave_api"} and cfg.search_free_only and not cfg.search_paid_providers_enabled:
        return True
    disabled_until = _TEMPORARILY_DISABLED_PROVIDERS.get(provider)
    if disabled_until is None:
        return False
    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts < disabled_until:
        return True
    _TEMPORARILY_DISABLED_PROVIDERS.pop(provider, None)
    return False



def _is_searxng_captcha_or_non_json_error(message: str) -> bool:
    normalized = (message or "").lower()
    return any(keyword in normalized for keyword in _SEARXNG_DEGRADED_KEYWORDS)


def _build_searxng_degraded_diagnostic(messages: list[str]) -> dict[str, Any] | None:
    if not messages:
        return None
    joined = " | ".join(str(item) for item in messages if str(item).strip())
    if not joined:
        return None
    category = _SEARXNG_DEGRADED_ERROR_CATEGORY if _is_searxng_captcha_or_non_json_error(joined) else "searxng_provider_degraded"
    message = joined
    if category == _SEARXNG_DEGRADED_ERROR_CATEGORY:
        message = (
            "SearXNG returned CAPTCHA/non-JSON-prone engine diagnostics; "
            "duckduckgo/startpage CAPTCHA or malformed JSON may be involved. "
            f"Details: {joined}"
        )
    return {
        "provider": "searxng",
        "provider_status": "degraded",
        "error_category": category,
        "message": message,
        "hint": _SEARXNG_DEGRADED_HINT,
        "event_type": "web_search_provider_degraded",
        "payload": {
            "provider": "searxng",
            "error_category": category,
            "hint": _SEARXNG_DEGRADED_HINT,
        },
    }


def _engine_list_from_param(engines_param: str | None) -> list[str]:
    return _split_engine_csv(engines_param or "")


def _extract_engine_names_from_error(message: str, engines: list[str]) -> list[str]:
    normalized = str(message or "").lower()
    return [engine for engine in engines if engine.lower() in normalized]


def _run_searxng_search(
    *,
    cfg: Any,
    queries: list[str],
    result_cap: int,
    search_lang: str,
    engines_param: str | None = None,
    engine_health_tracker: EngineHealthTracker | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, list[dict[str, Any]], dict[str, Any]]:
    base_url = cfg.searxng_url.rstrip("/")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    had_connection_failure = False
    diagnostics: list[dict[str, Any]] = []
    requested_engines = _engine_list_from_param(engines_param)
    fallback_to_safe = False

    for query in queries:
        query_engines = list(requested_engines)
        if engine_health_tracker and query_engines:
            query_engines, used_safe = engine_health_tracker.filter_engines(query_engines)
            fallback_to_safe = fallback_to_safe or used_safe
        effective_engines_param = ",".join(query_engines) if query_engines else (engines_param or "")
        query_params = {
            "q": query,
            "format": "json",
            "language": search_lang,
            "categories": "general",
        }
        if effective_engines_param:
            query_params["engines"] = effective_engines_param
        params = parse.urlencode(query_params)
        req = request.Request(f"{base_url}{_SEARXNG_ENDPOINT_PATH}?{params}", headers={"Accept": "application/json"}, method="GET")
        try:
            with request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                payload = json.loads(body)
        except json.JSONDecodeError as exc:
            had_connection_failure = True
            error_message = f"{query}: JSONDecodeError/non-JSON response: {exc}"
            errors.append(error_message)
            if engine_health_tracker:
                for engine in query_engines or requested_engines:
                    engine_health_tracker.record_error(engine, error_message)
            diagnostic = _build_searxng_degraded_diagnostic([error_message])
            if diagnostic:
                diagnostics.append(diagnostic)
            continue
        except urllib_error.HTTPError as exc:
            had_connection_failure = True
            body = exc.read().decode("utf-8", errors="replace")
            error_message = f"{query}: HTTP {exc.code} {exc.reason} {body[:500]}"
            errors.append(error_message)
            if engine_health_tracker:
                for engine in _extract_engine_names_from_error(error_message, query_engines or requested_engines) or (query_engines or requested_engines):
                    engine_health_tracker.record_error(engine, error_message)
            diagnostic = _build_searxng_degraded_diagnostic([error_message])
            if diagnostic:
                diagnostics.append(diagnostic)
            continue
        except Exception as exc:  # noqa: BLE001
            had_connection_failure = True
            error_message = f"{query}: {exc}"
            errors.append(error_message)
            if engine_health_tracker:
                for engine in _extract_engine_names_from_error(error_message, query_engines or requested_engines):
                    engine_health_tracker.record_error(engine, error_message)
            diagnostic = _build_searxng_degraded_diagnostic([error_message])
            if diagnostic:
                diagnostics.append(diagnostic)
            continue

        payload_errors = payload.get("errors") if isinstance(payload, dict) else None
        if payload_errors:
            payload_error_messages = [f"{query}: SearXNG engine error: {payload_errors}"]
            errors.extend(payload_error_messages)
            if engine_health_tracker:
                engine_health_tracker.record_payload_errors(payload_errors)
            diagnostic = _build_searxng_degraded_diagnostic(payload_error_messages)
            if diagnostic:
                diagnostics.append(diagnostic)

        results = payload.get("results") or []
        if not results and payload_errors:
            diagnostic = _build_searxng_degraded_diagnostic([f"{query}: zero results with SearXNG errors: {payload_errors}"])
            if diagnostic:
                diagnostics.append(diagnostic)
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
    health = engine_health_tracker.summary() if engine_health_tracker else {
        "broad_web_enabled": _allow_broad_web_engines(),
        "broad_web_engines": [e for e in requested_engines if e.lower() in _BROAD_WEB_ENGINES],
        "suspended_engines": [],
        "engine_failures": {},
        "fallback_to_safe_engines": fallback_to_safe,
    }
    health["fallback_to_safe_engines"] = bool(health.get("fallback_to_safe_engines") or fallback_to_safe)
    return items, errors, had_connection_failure, diagnostics, health


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


def _run_web_search(
    queries: list[str],
    *,
    mode: str = "standard",
    depth: str | None = None,
    max_results_per_query: int | None = None,
    scope: str | list[str] | None = None,
    language: str | None = None,
    country: str = "US",
    search_lang: str | None = None,
    source_profile: str | None = None,
    freshness: str | None = None,
    engine_health_tracker: EngineHealthTracker | None = None,
) -> dict[str, Any]:
    """Run configured web search provider and return a non-fatal normalized payload."""
    cfg = load_runtime_config()
    normalized_mode = _resolve_depth(mode, depth)
    mode_defaults = _SEARCH_MODE_SETTINGS[normalized_mode]
    result_cap = max_results_per_query if max_results_per_query is not None else mode_defaults["max_results_per_query"]
    result_cap = max(1, min(20, int(result_cap)))
    normalized_scope = _normalize_scope(scope)
    if source_profile is None and len(normalized_scope) == 1 and normalized_scope[0] in _PROFILE_SEARXNG_DEFAULTS:
        source_profile = normalized_scope[0]
    normalized_language = _normalize_language(language)
    effective_search_lang = _normalize_language(search_lang) if search_lang else normalized_language
    engine_resolution = resolve_searxng_engines_for_profile(source_profile, normalized_mode, freshness)

    normalized_queries = [q.strip() for q in queries if (q or "").strip()]
    effective_query_plan = {
        "requested_scope": scope,
        "normalized_scope": normalized_scope,
        "requested_language": language,
        "requested_depth": depth if depth is not None else mode,
        "resolved_depth": normalized_mode,
        "search_lang": effective_search_lang,
        "source_profile": engine_resolution.get("source_profile"),
        "engine_priority": engine_resolution.get("engine_priority"),
        "searxng_engines": engine_resolution.get("searxng_engines"),
        "freshness_policy": engine_resolution.get("freshness_policy"),
        "broad_web_enabled": engine_resolution.get("broad_web_enabled", False),
        "broad_web_engines": engine_resolution.get("broad_web_engines", []),
        "queries": normalized_queries,
        "generated_queries": normalized_queries,
    }

    configured_by_provider: dict[str, bool] = {}

    if not normalized_queries:
        selected_provider = (cfg.web_search_provider or "").strip().lower() or "unknown"
        response = {
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
            "source_profile": engine_resolution.get("source_profile"),
            "engine_priority": engine_resolution.get("engine_priority"),
            "searxng_engines": engine_resolution.get("searxng_engines"),
            "freshness_policy": engine_resolution.get("freshness_policy"),
            "items": [],
            "total_items": 0,
            "message": "query が空です。",
        }
        _store_last_web_search_status(response)
        return response

    if not cfg.enable_web:
        message = "NEXUS_ENABLE_WEB=false のため、Web検索は無効です。"
        response = {
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
            "source_profile": engine_resolution.get("source_profile"),
            "engine_priority": engine_resolution.get("engine_priority"),
            "searxng_engines": engine_resolution.get("searxng_engines"),
            "freshness_policy": engine_resolution.get("freshness_policy"),
            "items": _build_stub_items(normalized_queries, reason=message),
            "total_items": len(normalized_queries),
            "message": message,
            "non_fatal": True,
        }
        _store_last_web_search_status(response)
        return response

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
            configured_by_provider[provider] = provider not in {"brave","braveapi","brave_api"} or bool(cfg.brave_search_api_key)
            continue

        if provider in {"brave", "braveapi", "brave_api"} and not cfg.brave_search_api_key:
            provider_errors.setdefault(provider, []).append("Brave API is not configured.")
            configured_by_provider[provider] = False
            continue

        configured_by_provider[provider] = True
        attempted_providers.append(provider)
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        had_connection_failure = False
        should_cooldown = False
        diagnostics: list[dict[str, Any]] = []
        engine_health: dict[str, Any] = {}

        if provider == "searxng":
            items, errors, had_connection_failure, diagnostics, engine_health = _run_searxng_search(
                cfg=cfg,
                queries=normalized_queries,
                result_cap=result_cap,
                search_lang=effective_search_lang,
                engines_param=str(engine_resolution.get("searxng_engines_param") or ""),
                engine_health_tracker=engine_health_tracker,
            )
        elif provider in {"brave", "braveapi", "brave_api"}:
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
                "source_profile": engine_resolution.get("source_profile"),
                "engine_priority": engine_resolution.get("engine_priority"),
                "searxng_engines": engine_resolution.get("searxng_engines"),
                "freshness_policy": engine_resolution.get("freshness_policy"),
                **(engine_health or {"broad_web_enabled": engine_resolution.get("broad_web_enabled", False), "broad_web_engines": engine_resolution.get("broad_web_engines", []), "suspended_engines": [], "engine_failures": {}, "fallback_to_safe_engines": False}),
                "items": items,
                "total_items": len(items),
                "message": "ok",
            }
            if errors:
                response["errors"] = errors
            if diagnostics:
                response["provider_status"] = "degraded"
                response["diagnostics"] = diagnostics
                response["events"] = diagnostics
            _store_last_web_search_status(response)
            return response

        provider_errors[provider] = errors or ["結果が空のため、次の provider にフォールバックしました。"]
        if diagnostics:
            provider_errors[provider].extend(diag.get("message", "") for diag in diagnostics if diag.get("message"))
        if not had_connection_failure and not errors:
            provider_errors[provider].append("空結果フォールバック")

    message = "すべての検索 provider が失敗したため、non-fatal stub を返します。"
    selected_provider = attempted_providers[-1] if attempted_providers else (ordered_providers[0] if ordered_providers else cfg.web_search_provider)
    primary_provider = ordered_providers[0] if ordered_providers else cfg.web_search_provider
    stub_items = _build_stub_items(normalized_queries, reason=message)
    degraded_diagnostics = [
        diag
        for provider_errors_list in provider_errors.values()
        for diag in [_build_searxng_degraded_diagnostic([str(item) for item in provider_errors_list])]
        if diag
    ]
    response = {
        "provider": primary_provider,
        "selected_provider": selected_provider,
        "attempted_providers": attempted_providers,
        "fallback_used": bool(attempted_providers and selected_provider != primary_provider),
        "mode": normalized_mode,
        "configured": configured_by_provider.get(selected_provider, False),
        "effective_query_plan": effective_query_plan,
        "generated_queries": normalized_queries,
        "source_profile": engine_resolution.get("source_profile"),
        "engine_priority": engine_resolution.get("engine_priority"),
        "searxng_engines": engine_resolution.get("searxng_engines"),
        "freshness_policy": engine_resolution.get("freshness_policy"),
        **((engine_health_tracker.summary() if engine_health_tracker else {}) or {"broad_web_enabled": engine_resolution.get("broad_web_enabled", False), "broad_web_engines": engine_resolution.get("broad_web_engines", []), "suspended_engines": [], "engine_failures": {}, "fallback_to_safe_engines": False}),
        "items": stub_items,
        "total_items": len(stub_items),
        "message": message,
        "non_fatal": True,
        "provider_errors": provider_errors,
        "skipped_providers": skip_reasons,
    }
    if degraded_diagnostics:
        response["provider_status"] = "degraded"
        response["error_category"] = degraded_diagnostics[0].get("error_category")
        response["diagnostics"] = degraded_diagnostics
        response["events"] = degraded_diagnostics
    _store_last_web_search_status(response)
    return response


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
    source_profile: str | None = None,
    freshness: str | None = None,
    engine_health_tracker: EngineHealthTracker | None = None,
) -> dict[str, Any]:
    """内部用途の互換レイヤー（公開ツールではない）。実体は `_run_web_search(...)` を呼び出す。"""
    return _run_web_search(
        queries,
        mode=mode,
        depth=depth,
        max_results_per_query=max_results_per_query,
        scope=scope,
        language=language,
        country=country,
        search_lang=search_lang,
        source_profile=source_profile,
        freshness=freshness,
        engine_health_tracker=engine_health_tracker,
    )


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
