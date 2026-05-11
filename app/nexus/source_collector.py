from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
import re


_OFFICIAL_DOMAIN_SUFFIXES = (".gov", ".go.jp", ".europa.eu", ".int", ".edu", ".ac.jp", ".mil")
_OFFICIAL_DOMAIN_KEYWORDS = ("nasa.gov", "faa.gov", "easa.europa.eu", "icao.int", "iata.org", "energy.gov", "nrel.gov", "meti.go.jp", "nedo.go.jp")
_REPORT_TERMS = ("report", "white paper", "whitepaper", "annual report", "market report", "調査", "報告書", "白書")
_PAYWALL_TERMS = ("login", "signin", "subscribe", "paywall", "member-only", "会員限定")
_MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".mov", ".avi", ".mp3")


def _query_terms(text: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[\w\u3040-\u30ff\u3400-\u9fff]+", str(text or "")) if len(m.group(0)) >= 2}


def _is_official_domain(domain: str) -> bool:
    lowered = (domain or "").lower().strip()
    return lowered.endswith(_OFFICIAL_DOMAIN_SUFFIXES) or any(token in lowered for token in _OFFICIAL_DOMAIN_KEYWORDS)


def get_curated_domain_hints(query: str, source_profile: str = "web") -> list[str]:
    """Return safe curated domain/query hints for adaptive retrieval expansion."""
    q = str(query or "").lower()
    profile = str(source_profile or "web").lower()
    hints: list[str] = ["site:.gov", "site:.go.jp", "site:.europa.eu", "site:.int", "site:.org", "site:.edu", "site:.ac.jp"]
    if profile in {"market", "industry", "web", "news"}:
        hints.extend(["industry association", "market report", "annual report", "investor relations", "whitepaper", "roadmap", "forecast"])
    if profile in {"technical", "science", "web"}:
        hints.extend(["IEEE", "SAE", "NASA", "NEDO", "METI", "arxiv", "university", "research institute"])
    if any(token in q for token in ("航空", "航空機", "electric aircraft", "evtol", "aam", "advanced air mobility")):
        hints.extend([
            "nasa.gov", "faa.gov", "easa.europa.eu", "icao.int", "iata.org", "energy.gov", "nrel.gov",
            "aviationweek.com", "airbus.com", "boeing.com", "rolls-royce.com", "geaerospace.com",
            "magniX", "heart aerospace", "joby aviation", "archer", "beta technologies", "eVTOL", "advanced air mobility",
        ])
    if any(token in q for token in ("半導体", "sic", "gan", "diamond semiconductor", "ダイヤモンド半導体")):
        hints.extend([
            "semiconductors.org", "semi.org", "imec-int.com", "yolegroup.com", "infineon.com", "onsemi.com",
            "rohm.com", "st.com", "mitsubishielectric.com", "toshiba.semicon-storage.com", "meti.go.jp", "nedo.go.jp",
        ])
    unique: list[str] = []
    for hint in hints:
        if hint not in unique:
            unique.append(hint)
    return unique


def _normalize_url(raw_url: str) -> str:
    parsed = urlparse((raw_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    normalized_path = parsed.path or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{normalized_path}"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _domain_authority_score(domain: str) -> float:
    lowered = (domain or "").lower().strip()
    if not lowered:
        return 0.15

    high_confidence_suffixes = (
        ".gov",
        ".gov.us",
        ".go.jp",
        ".ac.jp",
        ".edu",
        ".edu.",
        ".mil",
        ".int",
    )
    high_confidence_keywords = ("iso.org", "ieee.org", "w3.org", "who.int", "oecd.org", "un.org")
    medium_confidence_keywords = (
        "nature.com",
        "science.org",
        "springer.com",
        "elsevier.com",
        "arxiv.org",
        "nih.gov",
        "nasa.gov",
    )
    low_confidence_keywords = ("blog", "medium.com", "note.com", "substack.com", "wordpress.com", "hatena")

    if lowered.endswith(high_confidence_suffixes) or any(keyword in lowered for keyword in high_confidence_keywords):
        return 1.0
    if any(keyword in lowered for keyword in medium_confidence_keywords):
        return 0.85
    if any(keyword in lowered for keyword in low_confidence_keywords):
        return 0.2
    if lowered.count(".") >= 1:
        return 0.55
    return 0.35


def _freshness_score(candidate: dict, now: datetime) -> float:
    raw = (
        candidate.get("published_at")
        or candidate.get("published_date")
        or candidate.get("date")
        or candidate.get("retrieved_at")
    )
    dt = _coerce_datetime(raw)
    if dt is None:
        return 0.35
    age_days = max((now - dt).total_seconds(), 0.0) / 86400.0
    if age_days <= 7:
        return 1.0
    if age_days <= 30:
        return 0.85
    if age_days <= 90:
        return 0.65
    if age_days <= 365:
        return 0.45
    return 0.2


def _content_type_score(candidate: dict, *, prefer_pdf: bool) -> float:
    url = str(candidate.get("url") or candidate.get("final_url") or "").lower()
    content_type = str(candidate.get("content_type") or "").lower()
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    metadata_content_type = str(metadata.get("content_type") or "").lower()
    detected = " ".join((url, content_type, metadata_content_type))

    if "pdf" in detected or url.endswith(".pdf"):
        return 1.0 if prefer_pdf else 0.8
    if any(token in detected for token in ("html", "htm", "text/plain", ".txt", "markdown", ".md")):
        return 0.75 if not prefer_pdf else 0.6
    if any(token in detected for token in ("doc", "docx", "ppt", "pptx", "xls", "xlsx")):
        return 0.5
    return 0.35


def compute_source_score(candidate: dict, prefer_pdf: bool, official_first: bool, now: datetime, query: str = "", trusted_domain_hints: list[str] | None = None) -> dict:
    """source候補の総合スコアを計算して内訳を返す。"""
    relevance = max(0.0, min(1.0, _safe_float(candidate.get("relevance_score"), 0.6)))
    url = str(candidate.get("url") or candidate.get("final_url") or "")
    lowered_url = url.lower()
    domain = urlparse(url).netloc.lower()
    title = str(candidate.get("title") or "")
    snippet = str(candidate.get("snippet") or "")
    haystack = f"{title} {snippet} {url}".lower()
    authority = _domain_authority_score(domain)
    official = _is_official_domain(domain)
    if official_first and official:
        authority = min(1.2, authority + 0.2)
    freshness = _freshness_score(candidate, now)
    content_type_priority = _content_type_score(candidate, prefer_pdf=prefer_pdf)
    is_pdf = "pdf" in haystack or lowered_url.endswith(".pdf")
    report_like = any(term in haystack for term in _REPORT_TERMS)
    query_overlap = 0.0
    q_terms = _query_terms(query)
    if q_terms:
        query_overlap = min(1.0, len(q_terms & _query_terms(haystack)) / max(1, min(len(q_terms), 8)))
    trusted_hints = trusted_domain_hints or []
    hint_match = 0.0
    for hint in trusted_hints:
        normalized_hint = str(hint or "").lower().replace("site:", "")
        if normalized_hint and (normalized_hint in domain or normalized_hint in haystack):
            hint_match = 1.0
            break
    citation_like = 0.35 if any(token in haystack for token in ("doi", "citation", "abstract", "journal", "proceedings")) else 0.0
    profile_match = 0.3 if any(token in haystack for token in ("market", "technical", "industry", "research", "forecast", "roadmap")) else 0.0
    penalties = 0.0
    if any(term in haystack for term in _PAYWALL_TERMS):
        penalties += 0.45
    if lowered_url.endswith(_MEDIA_EXTENSIONS):
        penalties += 0.7
    if any(term in haystack for term in ("image", "video", "gallery")) and lowered_url.endswith(_MEDIA_EXTENSIONS):
        penalties += 0.25
    quality_reasons: list[str] = []
    if official:
        quality_reasons.append("official_domain")
    if is_pdf:
        quality_reasons.append("pdf")
    if report_like:
        quality_reasons.append("report_or_whitepaper")
    if hint_match:
        quality_reasons.append("curated_domain_hint_match")
    if query_overlap:
        quality_reasons.append("query_overlap")
    if citation_like:
        quality_reasons.append("citation_like")

    score = relevance + authority + freshness + content_type_priority + (0.65 if is_pdf else 0.0) + (0.45 if report_like else 0.0) + query_overlap + hint_match + citation_like + profile_match - penalties
    rounded = round(score, 4)
    return {
        "source_score": rounded,
        "retrieval_score": rounded,
        "quality_reasons": quality_reasons,
        "is_official": official,
        "is_pdf": is_pdf,
        "source_score_breakdown": {
            "relevance": round(relevance, 4),
            "authority": round(authority, 4),
            "freshness": round(freshness, 4),
            "content_type_priority": round(content_type_priority, 4),
            "query_overlap": round(query_overlap, 4),
            "trusted_hint": round(hint_match, 4),
            "penalties": round(penalties, 4),
        },
    }


def collect_source_candidates(
    *,
    search_items: list[dict] | None = None,
    manual_urls: list[str] | None = None,
) -> list[dict]:
    """検索結果と手動URLを統合し、重複除去済みの source 候補を返す。"""
    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for item in search_items or []:
        normalized_url = _normalize_url(str(item.get("url") or ""))
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        metadata = dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {}
        metadata["is_stub"] = bool(item.get("is_stub") or metadata.get("is_stub"))
        candidates.append(
            {
                "url": normalized_url,
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("snippet") or ""),
                "provider": str(item.get("provider") or ""),
                "source_type": "web",
                "origin": "search",
                "relevance_score": _safe_float(item.get("relevance_score"), 0.6),
                "published_at": str(item.get("published_at") or item.get("published_date") or ""),
                "content_type": str(item.get("content_type") or ""),
                "metadata": metadata,
            }
        )

    for raw_url in manual_urls or []:
        normalized_url = _normalize_url(str(raw_url or ""))
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        candidates.append(
            {
                "url": normalized_url,
                "title": "",
                "snippet": "",
                "provider": "manual",
                "source_type": "web",
                "origin": "manual",
                "relevance_score": 0.7,
                "published_at": "",
                "content_type": "",
                "metadata": {},
            }
        )

    return candidates


def rank_source_candidates(
    candidates: list[dict],
    *,
    prefer_pdf: bool,
    official_first: bool,
    now: datetime | None = None,
    query: str = "",
    trusted_domain_hints: list[str] | None = None,
    max_per_domain: int = 5,
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    scored: list[dict] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        url = str(candidate.get("url") or candidate.get("final_url") or "")
        normalized_url = _normalize_url(url) or url
        duplicate = normalized_url in seen_urls
        seen_urls.add(normalized_url)
        metrics = compute_source_score(candidate, prefer_pdf=prefer_pdf, official_first=official_first, now=current, query=query, trusted_domain_hints=trusted_domain_hints)
        if duplicate:
            metrics["retrieval_score"] = round(_safe_float(metrics.get("retrieval_score")) - 1.0, 4)
            metrics.setdefault("quality_reasons", []).append("duplicate_url_penalty")
        scored.append({**candidate, **metrics})
    sorted_items = sorted(scored, key=lambda item: _safe_float(item.get("retrieval_score", item.get("source_score")), 0.0), reverse=True)
    domain_counts: dict[str, int] = {}
    diverse: list[dict] = []
    overflow: list[dict] = []
    for item in sorted_items:
        domain = urlparse(str(item.get("url") or item.get("final_url") or "")).netloc.lower()
        limit = max_per_domain + (2 if item.get("is_official") or item.get("is_pdf") else 0)
        if not domain:
            diverse.append(item)
            continue
        count = domain_counts.get(domain, 0)
        if count < limit:
            domain_counts[domain] = count + 1
            diverse.append(item)
        else:
            overflow.append(item)
    return [*diverse, *overflow]
