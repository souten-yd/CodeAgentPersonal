from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse


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


def compute_source_score(candidate: dict, prefer_pdf: bool, official_first: bool, now: datetime) -> dict:
    """source候補の総合スコアを計算して内訳を返す。"""
    relevance = max(0.0, min(1.0, _safe_float(candidate.get("relevance_score"), 0.6)))
    domain = urlparse(str(candidate.get("url") or candidate.get("final_url") or "")).netloc.lower()
    authority = _domain_authority_score(domain)
    if official_first:
        authority = min(1.0, authority + 0.1)
    freshness = _freshness_score(candidate, now)
    content_type_priority = _content_type_score(candidate, prefer_pdf=prefer_pdf)

    score = relevance + authority + freshness + content_type_priority
    return {
        "source_score": round(score, 4),
        "source_score_breakdown": {
            "relevance": round(relevance, 4),
            "authority": round(authority, 4),
            "freshness": round(freshness, 4),
            "content_type_priority": round(content_type_priority, 4),
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
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
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
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    scored: list[dict] = []
    for candidate in candidates:
        metrics = compute_source_score(candidate, prefer_pdf=prefer_pdf, official_first=official_first, now=current)
        scored.append({**candidate, **metrics})
    return sorted(scored, key=lambda item: _safe_float(item.get("source_score"), 0.0), reverse=True)
