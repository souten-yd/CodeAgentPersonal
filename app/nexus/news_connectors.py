from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib import parse, request
from xml.etree import ElementTree

RSS_FEEDS_PATH = Path("config/lumen/rss_feeds.json")
DEFAULT_PROVIDERS = ["gdelt", "searxng", "rss"]
API_KEY_REQUIRED_PROVIDERS: set[str] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class NormalizedNewsItem:
    title: str
    url: str
    source_name: str
    source_domain: str
    provider: str
    published_at: str | None
    language: str | None
    country: str | None
    category: str | None
    snippet: str | None
    image_url: str | None
    rights: dict[str, Any]
    raw: dict[str, Any]


@dataclass(slots=True)
class NewsSourceQuery:
    query: str
    language: str | None = None
    country: str | None = None
    category: str | None = None
    max_items: int = 10
    mode: str = "standard"


@dataclass(slots=True)
class NewsSourceResult:
    provider: str
    query: NewsSourceQuery
    items: list[NormalizedNewsItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class NewsConnectorError(RuntimeError):
    pass


class BaseNewsConnector:
    provider = "base"
    requires_api_key = False

    def search(self, query: NewsSourceQuery) -> NewsSourceResult:  # pragma: no cover - interface
        raise NotImplementedError


def default_rights(source_type: str, *, personal_use_only: bool = False, note: str = "") -> dict[str, Any]:
    return {
        "source_type": source_type,
        "personal_use_only": bool(personal_use_only),
        "allow_public_redistribution": False,
        "full_text_allowed": False,
        "provider_terms_note": note,
    }


def _domain(url: str) -> str:
    host = parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _http_json(url: str, *, timeout: int = 10) -> dict[str, Any]:
    req = request.Request(url, headers={"User-Agent": "CodeAgentPersonal/NewsSourceLayer"})
    with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - no-key public feeds/search endpoints only
        data = resp.read(2_000_000).decode("utf-8", errors="replace")
    if data.lstrip().startswith("callback("):
        data = data[data.find("(") + 1 : data.rfind(")")]
    return json.loads(data)


def _http_text(url: str, *, timeout: int = 10) -> str:
    req = request.Request(url, headers={"User-Agent": "CodeAgentPersonal/NewsSourceLayer"})
    with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - RSS metadata only, no article scraping
        return resp.read(1_500_000).decode("utf-8", errors="replace")


class GdeltDocNewsConnector(BaseNewsConnector):
    """No-key GDELT DOC 2.0 connector for rolling news search metadata."""

    provider = "gdelt"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def search(self, query: NewsSourceQuery) -> NewsSourceResult:
        params = {
            "query": query.query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(max(1, min(query.max_items, 50))),
            "sort": "HybridRel",
        }
        if query.language:
            params["sourcelang"] = query.language
        url = f"{self.endpoint}?{parse.urlencode(params)}"
        result = NewsSourceResult(provider=self.provider, query=query, metadata={"endpoint": self.endpoint})
        try:
            payload = _http_json(url)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(str(exc))
            return result
        for article in payload.get("articles") or []:
            item_url = str(article.get("url") or "").strip()
            title = str(article.get("title") or "").strip()
            if not item_url or not title:
                continue
            result.items.append(
                NormalizedNewsItem(
                    title=title,
                    url=item_url,
                    source_name=str(article.get("source") or _domain(item_url)),
                    source_domain=_domain(item_url),
                    provider=self.provider,
                    published_at=str(article.get("seendate") or article.get("datetime") or "") or None,
                    language=query.language,
                    country=str(article.get("sourcecountry") or query.country or "") or None,
                    category=query.category,
                    snippet=str(article.get("snippet") or "") or None,
                    image_url=str(article.get("socialimage") or "") or None,
                    rights=default_rights("gdelt", note="GDELT DOC 2.0 public no-key metadata; article full text is not fetched."),
                    raw=article,
                )
            )
        return result


class SearxngNewsConnector(BaseNewsConnector):
    provider = "searxng"

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or os.environ.get("SEARXNG_URL") or os.environ.get("SEARXNG_ENDPOINT") or "").rstrip("/")

    def search(self, query: NewsSourceQuery) -> NewsSourceResult:
        result = NewsSourceResult(provider=self.provider, query=query, metadata={"endpoint": self.endpoint})
        if not self.endpoint:
            result.errors.append("SEARXNG_URL is not configured")
            return result
        params = {"q": query.query, "format": "json", "categories": "news"}
        if query.language:
            params["language"] = query.language
        try:
            payload = _http_json(f"{self.endpoint}/search?{parse.urlencode(params)}")
        except Exception as exc:  # noqa: BLE001
            result.errors.append(str(exc))
            return result
        for raw in (payload.get("results") or [])[: query.max_items]:
            item_url = str(raw.get("url") or "").strip()
            title = str(raw.get("title") or "").strip()
            if not item_url or not title:
                continue
            result.items.append(
                NormalizedNewsItem(
                    title=title,
                    url=item_url,
                    source_name=str(raw.get("engine") or _domain(item_url)),
                    source_domain=_domain(item_url),
                    provider=self.provider,
                    published_at=str(raw.get("publishedDate") or "") or None,
                    language=query.language,
                    country=query.country,
                    category=query.category,
                    snippet=str(raw.get("content") or "") or None,
                    image_url=str(raw.get("img_src") or "") or None,
                    rights=default_rights("searxng", note="SearXNG metasearch result metadata only; article full text is not fetched."),
                    raw=raw,
                )
            )
        return result


def load_rss_feed_configs(path: Path = RSS_FEEDS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("feeds") or [])


class RssNewsConnector(BaseNewsConnector):
    provider = "rss"

    def __init__(self, feeds: list[dict[str, Any]] | None = None) -> None:
        self.feeds = feeds if feeds is not None else load_rss_feed_configs()

    def search(self, query: NewsSourceQuery) -> NewsSourceResult:
        result = NewsSourceResult(provider=self.provider, query=query, metadata={"feed_count": len(self.feeds)})
        needle = query.query.lower().strip()
        for feed in self.feeds:
            try:
                xml_text = _http_text(str(feed.get("url") or ""), timeout=10)
                root = ElementTree.fromstring(xml_text)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{feed.get('name')}: {exc}")
                continue
            feed_rights = default_rights(
                "rss",
                personal_use_only=bool(feed.get("personal_use_only")),
                note="RSS metadata only: title/link/pubDate/description. No full-text scraping or feed redistribution.",
            )
            feed_rights["allow_public_redistribution"] = bool(feed.get("allow_public_redistribution", False))
            feed_rights["full_text_allowed"] = bool(feed.get("full_text_allowed", False))
            for node in root.findall(".//item")[: max(1, query.max_items)]:
                title = (node.findtext("title") or "").strip()
                link = (node.findtext("link") or "").strip()
                description = (node.findtext("description") or "").strip()
                if not title or not link:
                    continue
                haystack = f"{title} {description}".lower()
                if needle and needle not in haystack and "latest news" not in needle and "news" not in needle and "ニュース" not in needle:
                    continue
                result.items.append(
                    NormalizedNewsItem(
                        title=title,
                        url=link,
                        source_name=str(feed.get("name") or _domain(link)),
                        source_domain=_domain(link),
                        provider=self.provider,
                        published_at=(node.findtext("pubDate") or "").strip() or None,
                        language=str(feed.get("language") or "") or query.language,
                        country=str(feed.get("country") or "") or query.country,
                        category=str(feed.get("category") or "") or query.category,
                        snippet=description or None,
                        image_url=None,
                        rights=feed_rights.copy(),
                        raw={"feed": feed.get("name"), "title": title, "link": link, "pubDate": node.findtext("pubDate"), "description": description},
                    )
                )
                if len(result.items) >= query.max_items:
                    break
        return result


def _normalized_url_key(url: str) -> str:
    parsed = parse.urlparse(url.strip())
    query = parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered = [(k, v) for k, v in query if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", parse.urlencode(filtered), ""))


def _title_key(title: str) -> str:
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", " ", title.lower()).strip()[:96]


def dedupe_news_items(items: list[NormalizedNewsItem]) -> list[NormalizedNewsItem]:
    """Dedupe by normalized URL, source_domain/title pairs, and simple title similarity."""

    seen_urls: set[str] = set()
    seen_domain_titles: set[tuple[str, str]] = set()
    seen_titles: set[str] = set()
    deduped: list[NormalizedNewsItem] = []
    for item in items:
        url_key = _normalized_url_key(item.url)
        title_key = _title_key(item.title)
        domain_title = (item.source_domain, title_key)
        if url_key in seen_urls or domain_title in seen_domain_titles or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_domain_titles.add(domain_title)
        seen_titles.add(title_key)
        deduped.append(item)
    return deduped


def apply_news_source_diversity(items: list[NormalizedNewsItem], *, max_items: int) -> tuple[list[NormalizedNewsItem], dict[str, Any]]:
    """Limit source concentration: provider <=50%, source_domain <=40% of selected items."""

    limit = max(1, max_items)
    provider_cap = max(1, (limit + 1) // 2)  # provider diversity limit 50%
    domain_cap = max(1, int(limit * 0.4) or 1)  # source_domain diversity limit 40%
    provider_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    selected: list[NormalizedNewsItem] = []
    deferred: list[NormalizedNewsItem] = []
    for item in items:
        if provider_counts.get(item.provider, 0) >= provider_cap or domain_counts.get(item.source_domain, 0) >= domain_cap:
            deferred.append(item)
            continue
        selected.append(item)
        provider_counts[item.provider] = provider_counts.get(item.provider, 0) + 1
        domain_counts[item.source_domain] = domain_counts.get(item.source_domain, 0) + 1
        if len(selected) >= limit:
            break
    for item in deferred:
        if len(selected) >= limit:
            break
        selected.append(item)
        provider_counts[item.provider] = provider_counts.get(item.provider, 0) + 1
        domain_counts[item.source_domain] = domain_counts.get(item.source_domain, 0) + 1
    return selected, {"provider_counts": provider_counts, "source_domain_counts": domain_counts, "provider_cap": provider_cap, "domain_cap": domain_cap}


def collect_news_from_connectors(
    query: NewsSourceQuery,
    *,
    providers: list[str] | None = None,
    connectors: list[BaseNewsConnector] | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    provider_names = providers or DEFAULT_PROVIDERS
    connector_map: dict[str, BaseNewsConnector] = {"gdelt": GdeltDocNewsConnector(), "searxng": SearxngNewsConnector(), "rss": RssNewsConnector()}
    if connectors:
        connector_map.update({connector.provider: connector for connector in connectors})
    results: list[NewsSourceResult] = []
    all_items: list[NormalizedNewsItem] = []
    for provider in provider_names:
        connector = connector_map.get(provider)
        if connector is None or connector.requires_api_key:
            continue
        result = connector.search(query)
        results.append(result)
        all_items.extend(result.items)
    deduped = dedupe_news_items(all_items)
    diversified, diversity = apply_news_source_diversity(deduped, max_items=max_items or query.max_items)
    return {
        "query": query,
        "results": results,
        "items": diversified,
        "metadata": {
            "providers": provider_names,
            "default_providers": DEFAULT_PROVIDERS,
            "api_key_required_default_providers": sorted(API_KEY_REQUIRED_PROVIDERS),
            "deduped_count": len(deduped),
            "raw_count": len(all_items),
            "diversity": diversity,
            "retrieved_at": _now_iso(),
        },
    }
