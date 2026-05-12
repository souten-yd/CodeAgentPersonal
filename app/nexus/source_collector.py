from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
import re


_OFFICIAL_DOMAIN_SUFFIXES = (".gov", ".go.jp", ".europa.eu", ".int", ".edu", ".ac.jp", ".mil")
_OFFICIAL_DOMAIN_KEYWORDS = ("nasa.gov", "faa.gov", "easa.europa.eu", "icao.int", "iata.org", "energy.gov", "nrel.gov", "meti.go.jp", "nedo.go.jp")
_REPORT_TERMS = ("report", "white paper", "whitepaper", "annual report", "market report", "調査", "報告書", "白書")
_PAYWALL_TERMS = ("login", "signin", "subscribe", "paywall", "member-only", "会員限定")
_MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".mov", ".avi", ".mp3")

_CURATED_DIRECT_PROFILES = {"news", "market", "source"}
_CURATED_DIRECT_SOURCE_TYPES = {
    "company_newsroom",
    "press_release",
    "investor_relations",
    "annual_report",
    "industry_association",
    "government_agency",
    "market_report",
}
_TOPIC_ANCHORS: dict[str, tuple[str, ...]] = {
    "aviation_electrification": (
        "航空", "航空機", "電動化", "electric aircraft", "hybrid electric", "electric propulsion",
        "evtol", "e-vtol", "aam", "advanced air mobility", "urban air mobility", "air taxi",
        "magnix", "heart aerospace", "joby", "archer", "beta technologies",
    ),
    "semiconductor": (
        "半導体", "semiconductor", "semiconductors", "chip", "chips", "sic", "gan",
        "power semiconductor", "compound semiconductor", "diamond semiconductor", "ダイヤモンド半導体",
        "imec", "yole", "infineon", "onsemi", "rohm", "toshiba semicon",
    ),
}
_CURATED_DIRECT_SOURCE_REGISTRY: dict[str, list[dict[str, str]]] = {
    "aviation_electrification": [
        {"url": "https://www.nasa.gov/aeronautics/", "title": "NASA Aeronautics", "source_type_hint": "government_agency", "reason": "NASA aeronautics programs and official electric/hybrid aircraft research updates."},
        {"url": "https://www.faa.gov/aircraft/advanced_air_mobility", "title": "FAA Advanced Air Mobility", "source_type_hint": "government_agency", "reason": "FAA regulatory source for advanced air mobility and aircraft certification."},
        {"url": "https://www.easa.europa.eu/en/domains/innovation/air-mobility", "title": "EASA Innovative Air Mobility", "source_type_hint": "government_agency", "reason": "EASA policy and certification material for innovative/electric air mobility."},
        {"url": "https://www.icao.int/innovation/Pages/default.aspx", "title": "ICAO Innovation", "source_type_hint": "government_agency", "reason": "ICAO global aviation policy and innovation reference source."},
        {"url": "https://www.iata.org/en/programs/environment/", "title": "IATA Environment", "source_type_hint": "industry_association", "reason": "IATA industry association perspective on aviation sustainability and technology adoption."},
        {"url": "https://www.airbus.com/en/newsroom", "title": "Airbus Newsroom", "source_type_hint": "company_newsroom", "reason": "Airbus official newsroom for aircraft technology and market announcements."},
        {"url": "https://www.boeing.com/company/key-orgs/boeing-innovation", "title": "Boeing Innovation", "source_type_hint": "company_newsroom", "reason": "Boeing official innovation hub for aircraft technology initiatives."},
        {"url": "https://www.geaerospace.com/news", "title": "GE Aerospace News", "source_type_hint": "company_newsroom", "reason": "GE Aerospace official news for propulsion and aviation technology announcements."},
        {"url": "https://www.rolls-royce.com/media/press-releases.aspx", "title": "Rolls-Royce Press Releases", "source_type_hint": "press_release", "reason": "Rolls-Royce official press releases for propulsion and electric flight programs."},
        {"url": "https://www.magnix.aero/news", "title": "magniX News", "source_type_hint": "company_newsroom", "reason": "magniX official updates on electric propulsion products and partnerships."},
        {"url": "https://heartaerospace.com/newsroom/", "title": "Heart Aerospace Newsroom", "source_type_hint": "company_newsroom", "reason": "Heart Aerospace official newsroom for electric aircraft development."},
        {"url": "https://www.jobyaviation.com/news/", "title": "Joby Aviation News", "source_type_hint": "company_newsroom", "reason": "Joby Aviation official news for eVTOL commercialization and certification."},
        {"url": "https://www.archer.com/news", "title": "Archer News", "source_type_hint": "company_newsroom", "reason": "Archer official news for eVTOL programs and partnerships."},
        {"url": "https://www.beta.team/news", "title": "BETA Technologies News", "source_type_hint": "company_newsroom", "reason": "BETA Technologies official news for electric aircraft and charging ecosystem updates."},
    ],
    "semiconductor": [
        {"url": "https://www.meti.go.jp/english/policy/mono_info_service/semiconductor/index.html", "title": "METI Semiconductor Policy", "source_type_hint": "government_agency", "reason": "METI official policy source for semiconductor strategy and industrial support."},
        {"url": "https://www.nedo.go.jp/english/", "title": "NEDO", "source_type_hint": "government_agency", "reason": "NEDO official R&D funding and project source for semiconductor technologies."},
        {"url": "https://www.semi.org/en/resources", "title": "SEMI Resources", "source_type_hint": "industry_association", "reason": "SEMI industry association reports and market resources."},
        {"url": "https://www.semiconductors.org/resources/", "title": "Semiconductor Industry Association Resources", "source_type_hint": "industry_association", "reason": "SIA industry association resources and market/policy reports."},
        {"url": "https://www.imec-int.com/en/press", "title": "imec Press", "source_type_hint": "press_release", "reason": "imec official research institute press releases on advanced semiconductors."},
        {"url": "https://www.yolegroup.com/reports/", "title": "Yole Group Reports", "source_type_hint": "market_report", "reason": "Yole market reports for semiconductor supply chain and device markets."},
        {"url": "https://www.infineon.com/cms/en/about-infineon/press/", "title": "Infineon Press", "source_type_hint": "press_release", "reason": "Infineon official press releases for semiconductor products and investments."},
        {"url": "https://www.onsemi.com/company/news-media", "title": "onsemi News Media", "source_type_hint": "company_newsroom", "reason": "onsemi official news for semiconductor product and market announcements."},
        {"url": "https://www.rohm.com/news-detail", "title": "ROHM News", "source_type_hint": "company_newsroom", "reason": "ROHM official news source for semiconductor announcements."},
        {"url": "https://www.st.com/content/st_com/en/about/media-center/press-releases.html", "title": "STMicroelectronics Press Releases", "source_type_hint": "press_release", "reason": "STMicroelectronics official press releases for semiconductor products and corporate updates."},
        {"url": "https://www.mitsubishielectric.com/news/", "title": "Mitsubishi Electric News", "source_type_hint": "company_newsroom", "reason": "Mitsubishi Electric official news including power semiconductor announcements."},
        {"url": "https://toshiba.semicon-storage.com/ap-en/company/news.html", "title": "Toshiba Electronic Devices & Storage News", "source_type_hint": "company_newsroom", "reason": "Toshiba semiconductor official news and product announcements."},
    ],
}


def _query_terms(text: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[\w\u3040-\u30ff\u3400-\u9fff]+", str(text or "")) if len(m.group(0)) >= 2}


def _is_official_domain(domain: str) -> bool:
    lowered = (domain or "").lower().strip()
    return lowered.endswith(_OFFICIAL_DOMAIN_SUFFIXES) or any(token in lowered for token in _OFFICIAL_DOMAIN_KEYWORDS)


def _matched_topic_anchors(query: str, intent: dict | None = None) -> list[str]:
    q = " ".join(
        str(part or "")
        for part in (
            query,
            (intent or {}).get("normalized_topic") if isinstance(intent, dict) else "",
            (intent or {}).get("original_query") if isinstance(intent, dict) else "",
            " ".join((intent or {}).get("required_dimensions") or []) if isinstance(intent, dict) else "",
        )
    ).lower()
    matched: list[str] = []
    for anchor, terms in _TOPIC_ANCHORS.items():
        if any(term.lower() in q for term in terms):
            matched.append(anchor)
    return matched


def _candidate_anchor_terms(candidate: dict) -> list[str]:
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    terms: list[str] = []
    for key in ("topic_anchor_terms", "topic_anchors", "curated_topic_anchors"):
        raw = candidate.get(key) or metadata.get(key)
        if isinstance(raw, (list, tuple, set)):
            terms.extend(str(item).lower() for item in raw if str(item).strip())
        elif isinstance(raw, str) and raw.strip():
            terms.append(raw.lower())
    for anchor in candidate.get("curated_topic_anchor", metadata.get("curated_topic_anchor", "")), candidate.get("topic_anchor", metadata.get("topic_anchor", "")):
        if str(anchor or "").strip() in _TOPIC_ANCHORS:
            terms.extend(term.lower() for term in _TOPIC_ANCHORS[str(anchor).strip()])
    return list(dict.fromkeys(terms))


def _curated_candidate_matches_topic(candidate: dict, query: str) -> bool:
    if str(candidate.get("origin") or "") != "curated_direct_source":
        return True
    q = str(query or "").lower()
    haystack = f"{candidate.get('title') or ''} {candidate.get('snippet') or ''} {candidate.get('url') or candidate.get('final_url') or ''}".lower()
    anchor_terms = _candidate_anchor_terms(candidate)
    if anchor_terms:
        return any(term and term in q for term in anchor_terms)
    q_terms = _query_terms(q)
    return not q_terms or bool(q_terms & _query_terms(haystack))


def get_curated_domain_hints(query: str, source_profile: str = "web", *, include_url_candidates: bool = False) -> list[str] | dict[str, list[str]]:
    """Return safe curated domain/query hints, optionally including direct URL hints."""
    q = str(query or "").lower()
    profile = str(source_profile or "web").lower()
    hints: list[str] = ["site:.gov", "site:.go.jp", "site:.europa.eu", "site:.int", "site:.org", "site:.edu", "site:.ac.jp"]
    if profile in {"market", "industry", "web", "news"}:
        hints.extend(["industry association", "market report", "annual report", "investor relations", "whitepaper", "roadmap", "forecast"])
    if profile in {"official", "source"}:
        hints.extend(["official", "government report", "white paper", "PDF", "site:go.jp", "site:.gov", "annual report", "investor relations"])
    if profile in {"academic", "technical", "science", "web", "source"}:
        hints.extend(["IEEE", "SAE", "NASA", "NEDO", "METI", "arxiv", "university", "research institute", "review paper"])
    if any(token in q for token in ("航空", "航空機", "electric aircraft", "hybrid electric", "electric propulsion", "evtol", "aam", "advanced air mobility")):
        hints.extend([
            "nasa.gov", "faa.gov", "easa.europa.eu", "icao.int", "iata.org", "energy.gov", "nrel.gov",
            "aviationweek.com", "airbus.com", "boeing.com", "rolls-royce.com", "geaerospace.com",
            "magniX", "heart aerospace", "joby aviation", "archer", "beta technologies", "eVTOL", "advanced air mobility",
        ])
    if any(token in q for token in ("半導体", "semiconductor", "semiconductors", " chip", "chips", "sic", "gan", "diamond semiconductor", "ダイヤモンド半導体")):
        hints.extend([
            "semiconductors.org", "semi.org", "imec-int.com", "yolegroup.com", "infineon.com", "onsemi.com",
            "rohm.com", "st.com", "mitsubishielectric.com", "toshiba.semicon-storage.com", "meti.go.jp", "nedo.go.jp",
        ])
    unique: list[str] = []
    for hint in hints:
        if hint not in unique:
            unique.append(hint)
    if not include_url_candidates:
        return unique
    urls = [candidate["url"] for candidate in build_curated_direct_source_candidates(query, profile)]
    return {"domain_hints": unique, "url_candidates": urls}


def build_curated_direct_source_candidates(query: str, source_profile: str, intent: dict | None = None) -> list[dict]:
    """Build direct-source URL candidates for news/market/source profiles before body download."""
    profile = str(source_profile or "web").strip().lower()
    if profile not in _CURATED_DIRECT_PROFILES:
        return []
    candidates: list[dict] = []
    seen_urls: set[str] = set()
    for anchor in _matched_topic_anchors(query, intent):
        anchor_terms = list(_TOPIC_ANCHORS.get(anchor, ()))
        for row in _CURATED_DIRECT_SOURCE_REGISTRY.get(anchor, []):
            normalized_url = _normalize_url(str(row.get("url") or ""))
            if not normalized_url or normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            source_type_hint = str(row.get("source_type_hint") or "company_newsroom")
            if source_type_hint not in _CURATED_DIRECT_SOURCE_TYPES:
                source_type_hint = "company_newsroom"
            title = str(row.get("title") or normalized_url)
            reason = str(row.get("reason") or "Curated direct source for the query topic and source profile.")
            candidates.append(
                {
                    "url": normalized_url,
                    "title": title,
                    "snippet": f"{reason} Topic anchor: {anchor}.",
                    "provider": "curated_direct_source",
                    "source_type": "web",
                    "origin": "curated_direct_source",
                    "relevance_score": 0.78,
                    "published_at": "",
                    "content_type": "text/html",
                    "source_type_hint": source_type_hint,
                    "curated_reason": reason,
                    "expected_freshness": "latest_or_current" if source_type_hint in {"company_newsroom", "press_release"} else "current_or_reference",
                    "curated_topic_anchor": anchor,
                    "topic_anchor_terms": anchor_terms,
                    "metadata": {
                        "curated_direct_source": True,
                        "source_type_hint": source_type_hint,
                        "curated_reason": reason,
                        "expected_freshness": "latest_or_current" if source_type_hint in {"company_newsroom", "press_release"} else "current_or_reference",
                        "curated_topic_anchor": anchor,
                        "topic_anchor_terms": anchor_terms,
                    },
                }
            )
    return candidates


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


def _freshness_score(candidate: dict, now: datetime, source_profile: str = "general") -> tuple[float, str, list[str]]:
    raw = (
        candidate.get("published_at")
        or candidate.get("published_date")
        or candidate.get("publishedDate")
        or candidate.get("date")
        or candidate.get("age")
        or candidate.get("retrieved_at")
    )
    profile = str(source_profile or "general").strip().lower()
    dt = _coerce_datetime(raw)
    reasons: list[str] = []
    current_year = now.year
    if dt is None and isinstance(raw, str) and str(current_year) in raw:
        dt = datetime(current_year, 7, 1, tzinfo=timezone.utc)
        reasons.append("current_year_text")
    if dt is None:
        return 0.35, "unknown", reasons

    age_days = max((now - dt).total_seconds(), 0.0) / 86400.0
    if dt.year == current_year:
        reasons.append("current_year")
    if age_days <= 366:
        bucket = "fresh"
        reasons.append("last_12_months")
    elif age_days > 730:
        bucket = "stale"
    else:
        bucket = "older"

    if age_days <= 7:
        score = 1.0
    elif age_days <= 30:
        score = 0.85
    elif age_days <= 90:
        score = 0.65
    elif age_days <= 365:
        score = 0.5
    elif age_days <= 730:
        score = 0.32
    else:
        score = 0.12

    if profile in {"news", "market"}:
        if age_days <= 366:
            score = min(1.15, score + 0.25)
            reasons.append("recent_news_market_boost")
        elif age_days > 730:
            score = max(-0.25, score - 0.35)
            reasons.append("older_than_2_years_news_market_penalty")
    elif profile in {"official", "academic"}:
        if age_days > 730:
            score = max(0.2, score)
            reasons.append("official_academic_stale_floor")
    elif profile == "source" and age_days <= 730:
        score = min(1.0, score + 0.1)
        reasons.append("source_report_moderate_freshness")
    return score, bucket, reasons


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


def compute_source_score(candidate: dict, prefer_pdf: bool, official_first: bool, now: datetime, query: str = "", trusted_domain_hints: list[str] | None = None, source_profile: str = "general") -> dict:
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
    freshness, freshness_bucket, freshness_reasons = _freshness_score(candidate, now, source_profile)
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
    curated_direct_boost = 0.0
    if str(candidate.get("origin") or "") == "curated_direct_source" or bool((candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}).get("curated_direct_source")):
        curated_direct_boost = 0.85 if _curated_candidate_matches_topic(candidate, query) else -2.0
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
    if curated_direct_boost > 0:
        quality_reasons.append("curated_direct_source_boost")
    elif curated_direct_boost < 0:
        quality_reasons.append("curated_topic_anchor_mismatch")
    quality_reasons.extend(freshness_reasons)

    score = relevance + authority + freshness + content_type_priority + (0.65 if is_pdf else 0.0) + (0.45 if report_like else 0.0) + query_overlap + hint_match + citation_like + profile_match + curated_direct_boost - penalties
    rounded = round(score, 4)
    return {
        "source_score": rounded,
        "retrieval_score": rounded,
        "quality_reasons": quality_reasons,
        "is_official": official,
        "is_pdf": is_pdf,
        "freshness_score": round(freshness, 4),
        "freshness_bucket": freshness_bucket,
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
    direct_source_candidates: list[dict] | None = None,
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
                "published_at": str(item.get("published_at") or item.get("published_date") or item.get("publishedDate") or item.get("age") or ""),
                "publishedDate": str(item.get("publishedDate") or item.get("published_at") or item.get("published_date") or item.get("age") or ""),
                "content_type": str(item.get("content_type") or ""),
                "metadata": metadata,
            }
        )

    for item in direct_source_candidates or []:
        normalized_url = _normalize_url(str(item.get("url") or ""))
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        metadata = dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {}
        metadata["curated_direct_source"] = bool(item.get("origin") == "curated_direct_source" or metadata.get("curated_direct_source"))
        candidates.append(
            {
                **item,
                "url": normalized_url,
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("snippet") or ""),
                "provider": str(item.get("provider") or "curated_direct_source"),
                "source_type": str(item.get("source_type") or "web"),
                "origin": str(item.get("origin") or "curated_direct_source"),
                "relevance_score": _safe_float(item.get("relevance_score"), 0.78),
                "published_at": str(item.get("published_at") or ""),
                "content_type": str(item.get("content_type") or "text/html"),
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
    source_profile: str = "general",
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    scored: list[dict] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        if str(candidate.get("origin") or "") == "curated_direct_source" and not _curated_candidate_matches_topic(candidate, query):
            continue
        url = str(candidate.get("url") or candidate.get("final_url") or "")
        normalized_url = _normalize_url(url) or url
        duplicate = normalized_url in seen_urls
        seen_urls.add(normalized_url)
        metrics = compute_source_score(candidate, prefer_pdf=prefer_pdf, official_first=official_first, now=current, query=query, trusted_domain_hints=trusted_domain_hints, source_profile=source_profile)
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
