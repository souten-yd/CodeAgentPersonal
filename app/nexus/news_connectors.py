from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from html import unescape
from typing import Any
from urllib import parse, request
from xml.etree import ElementTree

RSS_FEEDS_PATH = Path("config/lumen/rss_feeds.json")
DEFAULT_PROVIDERS = ["google_news_rss", "nhk_rss", "yahoo_rss", "cnbc_rss", "bbc_rss", "gdelt", "searxng"]
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
    summary: str | None = None
    canonical_url: str | None = None
    source: str = ""
    publisher: str = ""
    fetched_at: str = ""
    retrieval_method: str = "metadata"
    license_note: str = ""

    def __post_init__(self) -> None:
        if self.summary is None:
            self.summary = self.snippet
        if self.canonical_url is None and self.provider != "google_news_rss":
            self.canonical_url = self.url
        if not self.source:
            self.source = self.source_name
        if not self.publisher:
            self.publisher = self.source_name
        if not self.fetched_at:
            self.fetched_at = _now_iso()
        if not self.retrieval_method:
            self.retrieval_method = "metadata"
        if not self.license_note:
            self.license_note = str((self.rights or {}).get("provider_terms_note") or "")


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


@dataclass(slots=True)
class RssFeedConfig:
    id: str
    name: str
    provider: str = "rss"
    url: str | None = None
    url_template: str | None = None
    category: str | None = None
    language: str | None = None
    country: str | None = None
    retrieval_method: str = "rss"
    license_note: str = "headline/summary only"
    personal_use_only: bool = False
    allow_public_redistribution: bool = False
    full_text_allowed: bool = False
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RssFeedConfig":
        return cls(
            id=str(data.get("id") or data.get("provider") or data.get("name") or "rss"),
            name=str(data.get("name") or data.get("id") or "RSS"),
            provider=str(data.get("provider") or "rss"),
            url=str(data.get("url") or "") or None,
            url_template=str(data.get("url_template") or "") or None,
            category=str(data.get("category") or "") or None,
            language=str(data.get("language") or "") or None,
            country=str(data.get("country") or "") or None,
            retrieval_method=str(data.get("retrieval_method") or "rss"),
            license_note=str(data.get("license_note") or "headline/summary only"),
            personal_use_only=bool(data.get("personal_use_only", False)),
            allow_public_redistribution=bool(data.get("allow_public_redistribution", False)),
            full_text_allowed=bool(data.get("full_text_allowed", False)),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "url": self.url,
            "url_template": self.url_template,
            "category": self.category,
            "language": self.language,
            "country": self.country,
            "retrieval_method": self.retrieval_method,
            "license_note": self.license_note,
            "personal_use_only": self.personal_use_only,
            "allow_public_redistribution": self.allow_public_redistribution,
            "full_text_allowed": self.full_text_allowed,
            "enabled": self.enabled,
        }


def _load_rss_config_payload(path: Path = RSS_FEEDS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"profiles": {}, "feeds": []}
    return json.loads(path.read_text(encoding="utf-8"))


def load_rss_feed_profiles(path: Path = RSS_FEEDS_PATH) -> dict[str, list[str]]:
    data = _load_rss_config_payload(path)
    profiles = data.get("profiles") or {}
    return {str(name): [str(provider) for provider in providers] for name, providers in profiles.items()}


def load_rss_feed_configs(path: Path = RSS_FEEDS_PATH) -> list[dict[str, Any]]:
    data = _load_rss_config_payload(path)
    return list(data.get("feeds") or [])


def _load_rss_feed_config_objects(path: Path = RSS_FEEDS_PATH) -> list[RssFeedConfig]:
    return [RssFeedConfig.from_dict(feed) for feed in load_rss_feed_configs(path)]


def resolve_news_provider_profile(profile_name: str = "default", path: Path = RSS_FEEDS_PATH) -> list[str]:
    profiles = load_rss_feed_profiles(path)
    return list(profiles.get(profile_name) or profiles.get("default") or DEFAULT_PROVIDERS)


def _feed_matches_provider(feed: RssFeedConfig, provider_name: str) -> bool:
    if provider_name == "rss":
        return feed.provider == "rss"
    if feed.id == provider_name or feed.provider == provider_name:
        return True
    return provider_name == "yahoo_rss" and feed.id.startswith("yahoo_rss")


def _rss_rights(feed: RssFeedConfig) -> dict[str, Any]:
    rights = default_rights("rss", personal_use_only=feed.personal_use_only, note=feed.license_note)
    rights["allow_public_redistribution"] = feed.allow_public_redistribution
    rights["full_text_allowed"] = feed.full_text_allowed
    rights["license_note"] = feed.license_note
    rights["retrieval_method"] = feed.retrieval_method
    return rights


def extract_canonical_url_from_rss_item(node: ElementTree.Element) -> str | None:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "source":
            source_url = (child.attrib.get("url") or "").strip()
            if source_url:
                return source_url
        if tag in {"origLink", "canonical", "link"}:
            text = (child.text or "").strip()
            if text and not text.startswith("https://news.google.com/") and not text.startswith("http://news.google.com/"):
                return text
    guid = (node.findtext("guid") or "").strip()
    if guid.startswith("http") and "news.google.com" not in guid:
        return guid
    description = unescape((node.findtext("description") or "").strip())
    match = re.search(r'href=["\']([^"\']+)["\']', description)
    if match and "news.google.com" not in match.group(1):
        return match.group(1)
    return None


def _rss_source_text(node: ElementTree.Element) -> str:
    for child in list(node):
        if child.tag.rsplit("}", 1)[-1] == "source":
            return (child.text or "").strip()
    return ""


def normalize_rss_item(
    node: ElementTree.Element,
    feed: RssFeedConfig | dict[str, Any],
    *,
    provider: str | None = None,
    url_override: str | None = None,
    source_override: str | None = None,
    publisher_override: str | None = None,
) -> NormalizedNewsItem | None:
    cfg = feed if isinstance(feed, RssFeedConfig) else RssFeedConfig.from_dict(feed)
    title = (node.findtext("title") or "").strip()
    link = (url_override or node.findtext("link") or "").strip()
    summary = (node.findtext("description") or "").strip() or None
    if not title or not link:
        return None
    canonical_url = extract_canonical_url_from_rss_item(node)
    if provider != "google_news_rss" and not canonical_url:
        canonical_url = link
    publisher = publisher_override or _rss_source_text(node) or cfg.name
    source = source_override or cfg.name
    source_domain = _domain(canonical_url or link)
    rights = _rss_rights(cfg)
    fetched_at = _now_iso()
    return NormalizedNewsItem(
        title=title,
        url=link,
        source_name=source,
        source_domain=source_domain,
        provider=provider or cfg.id,
        published_at=(node.findtext("pubDate") or node.findtext("published") or "").strip() or None,
        language=cfg.language,
        country=cfg.country,
        category=cfg.category,
        snippet=summary,
        image_url=None,
        rights=rights,
        raw={"feed": cfg.to_dict(), "title": title, "link": link, "pubDate": node.findtext("pubDate"), "description": summary},
        summary=summary,
        canonical_url=canonical_url,
        source=source,
        publisher=publisher,
        fetched_at=fetched_at,
        retrieval_method=cfg.retrieval_method,
        license_note=cfg.license_note,
    )


class GoogleNewsRssConnector(BaseNewsConnector):
    provider = "google_news_rss"

    def __init__(self, feed: RssFeedConfig | dict[str, Any] | None = None) -> None:
        if feed is None:
            feeds = [RssFeedConfig.from_dict(raw) for raw in load_rss_feed_configs()]
            feed = next((cfg for cfg in feeds if cfg.id == self.provider), None)
        self.feed = feed if isinstance(feed, RssFeedConfig) else RssFeedConfig.from_dict(feed or {"id": self.provider, "name": "Google News RSS Search", "provider": self.provider})

    def search(self, query: NewsSourceQuery) -> NewsSourceResult:
        result = NewsSourceResult(provider=self.provider, query=query, metadata={"feed_id": self.feed.id, "aggregator": True})
        if not self.feed.url_template:
            result.errors.append("Google News RSS url_template is not configured")
            return result
        url = self.feed.url_template.format(query=parse.quote(query.query))
        result.metadata["endpoint_configured"] = True
        try:
            root = ElementTree.fromstring(_http_text(url, timeout=10))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(str(exc))
            return result
        for node in root.findall(".//item")[: max(1, query.max_items)]:
            publisher = _rss_source_text(node) or "Google News"
            item = normalize_rss_item(node, self.feed, provider=self.provider, source_override="Google News", publisher_override=publisher)
            if item is not None:
                item.raw["google_news_url"] = item.url
                item.raw["aggregator"] = True
                result.items.append(item)
        return result


class RssNewsConnector(BaseNewsConnector):
    provider = "rss"

    def __init__(self, feeds: list[dict[str, Any] | RssFeedConfig] | None = None, *, provider_name: str = "rss") -> None:
        self.provider = provider_name
        configs = feeds if feeds is not None else _load_rss_feed_config_objects()
        self.feeds = [feed if isinstance(feed, RssFeedConfig) else RssFeedConfig.from_dict(feed) for feed in configs]
        self.feeds = [feed for feed in self.feeds if _feed_matches_provider(feed, provider_name)]

    def search(self, query: NewsSourceQuery) -> NewsSourceResult:
        result = NewsSourceResult(provider=self.provider, query=query, metadata={"feed_count": len(self.feeds), "endpoint_configured": bool(self.feeds)})
        needle = query.query.lower().strip()
        for feed in self.feeds:
            if not feed.enabled or not feed.url or feed.url == "CONFIGURE_VALIDATED_NHK_RSS_URL":
                result.metadata.setdefault("skipped_feeds", []).append(feed.id)
                result.errors.append(f"{feed.id}: skipped disabled or unvalidated RSS URL")
                continue
            try:
                xml_text = _http_text(feed.url, timeout=10)
                root = ElementTree.fromstring(xml_text)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{feed.name}: {exc}")
                continue
            for node in root.findall(".//item")[: max(1, query.max_items)]:
                item = normalize_rss_item(node, feed, provider=self.provider)
                if item is None:
                    continue
                haystack = f"{item.title} {item.summary or ''}".lower()
                if needle and needle not in haystack and "latest news" not in needle and "news" not in needle and "ニュース" not in needle:
                    continue
                result.items.append(item)
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


def _provider_status(result: NewsSourceResult | None, provider: str, *, skipped: bool = False, skip_reason: str = "", endpoint_configured: bool = True) -> dict[str, Any]:
    errors = list(result.errors if result is not None else ([] if not skip_reason else [skip_reason]))
    configured = bool((result.metadata or {}).get("endpoint_configured", endpoint_configured)) if result is not None else endpoint_configured
    if provider == "searxng" and result is not None and not (result.metadata or {}).get("endpoint"):
        configured = False
    skipped_feeds = list((result.metadata or {}).get("skipped_feeds") or []) if result is not None else []
    is_skipped = skipped or bool(skipped_feeds)
    reason = skip_reason or ("; ".join(skipped_feeds) if skipped_feeds else "")
    return {
        "provider": provider,
        "ok": bool(result is not None and result.items and not errors),
        "item_count": len(result.items) if result is not None else 0,
        "error_count": len(errors),
        "errors": errors,
        "skipped": is_skipped,
        "skip_reason": reason,
        "endpoint_configured": configured,
        "retrieved_at": _now_iso(),
    }


def _overall_status(provider_status: list[dict[str, Any]]) -> str:
    if any(status.get("item_count", 0) > 0 for status in provider_status):
        if any(status.get("error_count", 0) or status.get("skipped") or not status.get("endpoint_configured", True) for status in provider_status):
            return "degraded"
        return "ok"
    return "degraded" if provider_status else "failed"


def collect_news_from_connectors(
    query: NewsSourceQuery,
    *,
    providers: list[str] | None = None,
    connectors: list[BaseNewsConnector] | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    provider_names = providers or DEFAULT_PROVIDERS
    connector_map: dict[str, BaseNewsConnector] = {
        "google_news_rss": GoogleNewsRssConnector(),
        "nhk_rss": RssNewsConnector(provider_name="nhk_rss"),
        "yahoo_rss": RssNewsConnector(provider_name="yahoo_rss"),
        "cnbc_rss": RssNewsConnector(provider_name="cnbc_rss"),
        "bbc_rss": RssNewsConnector(provider_name="bbc_rss"),
        "gdelt": GdeltDocNewsConnector(),
        "searxng": SearxngNewsConnector(),
        "rss": RssNewsConnector(),
    }
    if connectors:
        connector_map.update({connector.provider: connector for connector in connectors})
    results: list[NewsSourceResult] = []
    statuses: list[dict[str, Any]] = []
    all_items: list[NormalizedNewsItem] = []
    for provider in provider_names:
        connector = connector_map.get(provider)
        if connector is None:
            statuses.append(_provider_status(None, provider, skipped=True, skip_reason="provider connector is not registered", endpoint_configured=False))
            continue
        if connector.requires_api_key:
            statuses.append(_provider_status(None, provider, skipped=True, skip_reason="provider requires an API key", endpoint_configured=False))
            continue
        result = connector.search(query)
        results.append(result)
        all_items.extend(result.items)
        statuses.append(_provider_status(result, provider))
    deduped = dedupe_news_items(all_items)
    diversified, diversity = apply_news_source_diversity(deduped, max_items=max_items or query.max_items)
    overall = _overall_status(statuses)
    return {
        "query": query,
        "results": results,
        "items": diversified,
        "provider_status": statuses,
        "overall_status": overall,
        "metadata": {
            "providers": provider_names,
            "default_providers": DEFAULT_PROVIDERS,
            "api_key_required_default_providers": sorted(API_KEY_REQUIRED_PROVIDERS),
            "deduped_count": len(deduped),
            "raw_count": len(all_items),
            "diversity": diversity,
            "provider_status": statuses,
            "overall_status": overall,
            "retrieved_at": _now_iso(),
        },
    }
