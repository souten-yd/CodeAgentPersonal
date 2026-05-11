from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

_CITATION_RE = re.compile(r"\[(S\d+)\]")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+")


TEXT_SUPPORT_THRESHOLD = 0.25
CITATION_TEXT_SUPPORT_THRESHOLD = 0.18
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MARKDOWN_RE = re.compile(r"[`*_~>#|]+")
_ALNUM_RE = re.compile(r"[a-z0-9][a-z0-9_.+-]*", re.IGNORECASE)
_JA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]+")


def _normalize_citation_label(label: Any) -> str:
    raw = str(label or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("[") and raw.endswith("]") else f"[{raw.strip('[]')}]"


def normalize_text_for_overlap(text: str) -> str:
    """Normalize claim/evidence text for deterministic overlap scoring."""
    normalized = str(text or "").lower()
    normalized = _URL_RE.sub(" ", normalized)
    normalized = _CITATION_RE.sub(" ", normalized)
    normalized = _MARKDOWN_RE.sub(" ", normalized)
    normalized = re.sub(r"[\[\](){},:;!?！？。、「」『』・/\\]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize_claim_text(text: str) -> list[str]:
    """Extract compact alphanumeric tokens plus Japanese character n-grams."""
    normalized = normalize_text_for_overlap(text)
    tokens: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        token = token.strip("._+-")
        if len(token) < 2 or token in seen:
            return
        seen.add(token)
        tokens.append(token)

    for match in _ALNUM_RE.finditer(normalized):
        add(match.group(0))
        if len(tokens) >= 80:
            return tokens[:80]

    for match in _JA_RE.finditer(normalized):
        segment = match.group(0)
        if len(segment) < 2:
            continue
        max_n = min(6, len(segment))
        for n in range(2, max_n + 1):
            for idx in range(0, len(segment) - n + 1):
                add(segment[idx : idx + n])
                if len(tokens) >= 80:
                    return tokens[:80]
    return tokens[:80]


def compute_text_overlap_score(claim: str, evidence_text: str) -> float:
    """Return a lightweight containment/Jaccard overlap score from 0.0 to 1.0."""
    claim_tokens = set(tokenize_claim_text(claim))
    evidence_tokens = set(tokenize_claim_text(evidence_text))
    if len(claim_tokens) < 2 or not evidence_tokens:
        return 0.0
    overlap = claim_tokens & evidence_tokens
    if not overlap:
        return 0.0
    containment = len(overlap) / len(claim_tokens)
    jaccard = len(overlap) / len(claim_tokens | evidence_tokens)
    return round(max(containment, jaccard), 4)


def _claim_citations(claim: dict[str, Any]) -> list[str]:
    labels = [_normalize_citation_label(label) for label in claim.get("citations") or []]
    text = str(claim.get("claim") or claim.get("text") or "")
    labels.extend(f"[{label}]" for label in _CITATION_RE.findall(text))
    return [label for label in dict.fromkeys(labels) if label]


def _evidence_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("quote", "text", "snippet", "summary", "title", "publisher")
        if row.get(key)
    )


def _row_source_id(row: dict[str, Any]) -> str:
    return str(row.get("source_id") or row.get("id") or row.get("url") or "").strip()


def _best_title(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("title") or row.get("publisher") or row.get("url") or "")




def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _domain_from_row(row: dict[str, Any]) -> str:
    raw = str(row.get("domain") or "").strip().lower()
    if raw:
        return raw.removeprefix("www.")
    url = str(row.get("final_url") or row.get("url") or "").strip()
    if url:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return str(parsed.netloc or "").lower().removeprefix("www.")
    return ""


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def score_source_quality(source_or_evidence: dict) -> dict:
    """Score source/evidence quality using deterministic metadata heuristics."""
    row = source_or_evidence if isinstance(source_or_evidence, dict) else {}
    reasons: list[str] = []
    score = 0.35
    domain = _domain_from_row(row)
    publisher = str(row.get("publisher") or row.get("source") or "").lower()
    title = str(row.get("title") or "").lower()
    content_type = str(row.get("content_type") or row.get("mime_type") or "").lower()
    url = str(row.get("final_url") or row.get("url") or "").lower()
    status = str(row.get("status") or "").lower()
    body = _evidence_text(row)
    is_official = bool(row.get("is_official"))
    official_domain = domain.endswith((".gov", ".go.jp", ".edu", ".ac.jp", ".int")) or ".go." in domain
    is_pdf = "pdf" in content_type or url.endswith(".pdf")
    is_degraded = status in {"failed", "degraded", "skipped"}

    if is_official or official_domain:
        score += 0.30
        reasons.append("official_or_public_institution_domain")
        is_official = True
    if is_pdf or any(token in title or token in url for token in ("report", "whitepaper", "white-paper")):
        score += 0.16
        reasons.append("pdf_or_report_like_source")
        is_pdf = True
    if any(token in publisher for token in ("government", "ministry", "agency", "university", "institute", "company official", "official")):
        score += 0.14
        reasons.append("authoritative_publisher")
    if is_degraded:
        score -= 0.35
        reasons.append(f"status_{status}")
    if not content_type:
        score -= 0.08
        reasons.append("missing_content_type")
    if len(body.strip()) < 20:
        score -= 0.16
        reasons.append("very_short_evidence_text")
    elif len(body.strip()) < 80:
        score -= 0.06
        reasons.append("short_evidence_text")
    is_fresh: bool | None = None
    retrieved_or_published = _parse_iso_datetime(row.get("published_at")) or _parse_iso_datetime(row.get("retrieved_at"))
    if retrieved_or_published:
        age_days = (datetime.now(timezone.utc) - retrieved_or_published).days
        is_fresh = age_days <= 365 * 3
        if is_fresh:
            score += 0.08
            reasons.append("fresh_within_three_years")
    if domain and any(token in domain for token in ("blog", "forum")):
        score -= 0.05
        reasons.append("blog_or_forum_domain")
    if not domain and not row.get("source_id") and not row.get("citation_label") and len(body.strip()) < 20:
        quality_level = "unknown"
        score = 0.0
    else:
        score = round(_clamp(score), 4)
        if score >= 0.75:
            quality_level = "high"
        elif score >= 0.45:
            quality_level = "medium"
        else:
            if score <= 0:
                score = 0.01
            quality_level = "low"

    return {
        "quality_score": float(score),
        "quality_level": quality_level,
        "quality_reasons": reasons,
        "is_official": bool(is_official),
        "is_pdf": bool(is_pdf),
        "is_degraded": bool(is_degraded),
        "is_fresh": is_fresh,
        "source_id": _row_source_id(row),
        "citation_label": _normalize_citation_label(row.get("citation_label") or row.get("label")),
        "domain": domain,
    }


def build_source_quality_index(sources: list[dict], evidence_chunks: list[dict], references: list[dict]) -> dict[str, dict]:
    """Build a quality lookup keyed by source id, citation label, and URL-like ids."""
    index: dict[str, dict] = {}
    rows = list(sources or []) + list(evidence_chunks or []) + list(references or [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        quality = score_source_quality(row)
        keys = [
            _row_source_id(row),
            _normalize_citation_label(row.get("citation_label") or row.get("label")),
            str(row.get("url") or "").strip(),
            str(row.get("final_url") or "").strip(),
        ]
        for key in [k for k in keys if k]:
            current = index.get(key)
            if current is None or float(quality.get("quality_score") or 0.0) > float(current.get("quality_score") or 0.0):
                index[key] = quality
    return index


def summarize_supporting_source_quality(
    claim: dict, sources: list[dict], evidence_chunks: list[dict], references: list[dict]
) -> dict:
    """Summarize quality for sources attached to a verified claim."""
    index = build_source_quality_index(sources, evidence_chunks, references)
    keys: list[str] = []
    for source_id in claim.get("supporting_source_ids") or []:
        if source_id:
            keys.append(str(source_id))
    for label in _claim_citations(claim):
        keys.append(label)
    best_label = _normalize_citation_label(claim.get("best_evidence_citation_label"))
    if best_label:
        keys.append(best_label)
    qualities = [index[key] for key in dict.fromkeys(keys) if key in index]
    scores = [float(q.get("quality_score") or 0.0) for q in qualities if q.get("quality_level") != "unknown"]
    reasons: list[str] = []
    for q in qualities:
        for reason in q.get("quality_reasons") or []:
            if reason not in reasons:
                reasons.append(str(reason))
    high_count = sum(1 for q in qualities if q.get("quality_level") == "high")
    low_count = sum(1 for q in qualities if q.get("quality_level") == "low")
    return {
        "best_quality_score": max(scores) if scores else 0.0,
        "average_quality_score": (sum(scores) / len(scores)) if scores else 0.0,
        "high_quality_source_count": high_count,
        "low_quality_source_count": low_count,
        "quality_reasons": reasons[:12],
    }


_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_DATE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}[-/年](?:0?[1-9]|1[0-2])(?:[-/月](?:0?[1-9]|[12]\d|3[01])日?)?")
_PERCENT_RE = re.compile(r"(?<!\w)\d+(?:\.\d+)?\s*[％%]")
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:億|万|兆|千|百|million|billion|trillion)?")
_NEGATION_TERMS = ("ない", "未定", "否定", "不可能", "中止", "撤回", "延期", "no", "not", "never", "cancelled", "canceled", "withdrawn")
_MODAL_TERMS = ("予定", "目標", "見込み", "可能性", "以降", "expected", "plan", "planned", "target", "may", "might", "could")


def extract_numeric_and_temporal_signals(text: str) -> dict:
    raw = str(text or "")
    lowered = raw.lower()
    years = sorted({int(match.group(0)) for match in _YEAR_RE.finditer(raw)})
    dates = list(dict.fromkeys(match.group(0) for match in _DATE_RE.finditer(raw)))
    numbers = list(dict.fromkeys([m.group(0).strip() for m in _PERCENT_RE.finditer(raw)] + [m.group(0).strip() for m in _NUMBER_RE.finditer(raw)]))
    negation_terms = [term for term in _NEGATION_TERMS if term in lowered]
    modal_terms = [term for term in _MODAL_TERMS if term in lowered]
    return {
        "years": years,
        "numbers": numbers,
        "dates": dates,
        "negation_terms": negation_terms,
        "modal_terms": modal_terms,
    }


def _evidence_for_claim(claim: dict, evidence_chunks: list[dict], references: list[dict]) -> list[dict]:
    claim_text = str(claim.get("claim") or claim.get("text") or "")
    source_ids = {str(s) for s in claim.get("supporting_source_ids") or [] if s}
    citations = set(_claim_citations(claim))
    rows: list[dict] = []
    for row in list(evidence_chunks or []) + list(references or []):
        if not isinstance(row, dict):
            continue
        label = _normalize_citation_label(row.get("citation_label") or row.get("label"))
        source_id = _row_source_id(row)
        score = compute_text_overlap_score(claim_text, _evidence_text(row))
        if (source_id and source_id in source_ids) or (label and label in citations) or score >= CITATION_TEXT_SUPPORT_THRESHOLD:
            rows.append(row)
    return rows[:8]


def detect_claim_contradictions(claims: list[dict], evidence_chunks: list[dict], references: list[dict]) -> dict:
    contradictions: list[dict] = []
    for idx, claim in enumerate(claims or []):
        claim_text = str(claim.get("claim") or claim.get("text") or "")
        if not claim_text:
            continue
        claim_signals = extract_numeric_and_temporal_signals(claim_text)
        rows = _evidence_for_claim(claim, evidence_chunks, references)
        evidence_signals = [extract_numeric_and_temporal_signals(_evidence_text(row)) for row in rows]
        evidence_summaries = [
            {
                "source_id": _row_source_id(row),
                "citation_label": _normalize_citation_label(row.get("citation_label") or row.get("label")),
                "title": _best_title(row),
                "signals": signals,
            }
            for row, signals in zip(rows, evidence_signals)
        ]

        def add(kind: str, severity: str, signals: dict) -> None:
            contradictions.append(
                {
                    "claim": claim_text,
                    "claim_index": idx,
                    "type": kind,
                    "signals": signals,
                    "evidence": evidence_summaries[:5],
                    "severity": severity,
                }
            )

        claim_years = set(claim_signals["years"])
        evidence_years = {year for signals in evidence_signals for year in signals["years"]}
        if claim_years and evidence_years and not (claim_years & evidence_years):
            if min(abs(a - b) for a in claim_years for b in evidence_years) >= 1:
                add("year_mismatch", "medium", {"claim": claim_signals, "evidence_years": sorted(evidence_years)})
                continue
        elif claim_years:
            other_years = evidence_years - claim_years
            if other_years and any(abs(a - b) >= 1 for a in claim_years for b in other_years):
                add("year_mismatch", "low", {"claim": claim_signals, "evidence_years": sorted(evidence_years)})
                continue

        claim_numbers = set(claim_signals["numbers"])
        evidence_numbers = {num for signals in evidence_signals for num in signals["numbers"]}
        if claim_numbers and evidence_numbers and claim_numbers.isdisjoint(evidence_numbers):
            add("number_mismatch", "low", {"claim": claim_signals, "evidence_numbers": sorted(evidence_numbers)})
            continue

        evidence_negations = [term for signals in evidence_signals for term in signals["negation_terms"]]
        if evidence_negations and not claim_signals["negation_terms"]:
            add("negation_conflict", "medium", {"claim": claim_signals, "evidence_negation_terms": sorted(set(evidence_negations))})
            continue

        evidence_modals = [term for signals in evidence_signals for term in signals["modal_terms"]]
        if evidence_modals and not claim_signals["modal_terms"]:
            add("modal_uncertainty", "low", {"claim": claim_signals, "evidence_modal_terms": sorted(set(evidence_modals))})

    return {"contradiction_count": len(contradictions), "contradictions": contradictions}

def find_supporting_evidence_for_claim(
    claim: dict[str, Any], evidence_chunks: list[dict[str, Any]], references: list[dict[str, Any]]
) -> dict[str, Any]:
    claim_text = str(claim.get("claim") or claim.get("text") or "")
    citations = set(_claim_citations(claim))
    citation_rows = list(evidence_chunks or []) + list(references or [])
    labels_to_rows: dict[str, list[dict[str, Any]]] = {}
    for row in citation_rows:
        if not isinstance(row, dict):
            continue
        label = _normalize_citation_label(row.get("citation_label") or row.get("label"))
        if label:
            labels_to_rows.setdefault(label, []).append(row)

    cited_rows = [row for label in citations for row in labels_to_rows.get(label, [])]
    citation_exists = bool(cited_rows)
    best_score = 0.0
    best_evidence: dict[str, Any] | None = None
    matched_count = 0
    supporting_source_ids: list[str] = []

    for row in evidence_chunks or []:
        if not isinstance(row, dict):
            continue
        score = compute_text_overlap_score(claim_text, _evidence_text(row))
        if score >= CITATION_TEXT_SUPPORT_THRESHOLD:
            matched_count += 1
        if score > best_score:
            best_score = score
            best_evidence = row

    if citation_exists and best_score >= CITATION_TEXT_SUPPORT_THRESHOLD:
        support_type = "citation_and_text"
    elif citation_exists:
        support_type = "citation_only"
        if best_evidence is None and cited_rows:
            best_evidence = cited_rows[0]
    elif best_score >= TEXT_SUPPORT_THRESHOLD:
        support_type = "text_only"
    else:
        support_type = "none"

    if support_type in {"citation_and_text", "citation_only"}:
        for row in cited_rows:
            source_id = _row_source_id(row)
            if source_id and source_id not in supporting_source_ids:
                supporting_source_ids.append(source_id)
    if support_type in {"citation_and_text", "text_only"} and best_evidence:
        source_id = _row_source_id(best_evidence)
        if source_id and source_id not in supporting_source_ids:
            supporting_source_ids.append(source_id)

    return {
        "best_score": float(best_score),
        "best_evidence": best_evidence,
        "matched_evidence_count": matched_count,
        "supporting_source_ids": supporting_source_ids,
        "support_type": support_type,
    }


def verify_claim_support(
    claims: list[dict[str, Any]], evidence_chunks: list[dict[str, Any]], references: list[dict[str, Any]]
) -> dict[str, Any]:
    evaluated: list[dict[str, Any]] = []
    supported = weakly_supported = unsupported = unresolved = 0
    support_type_counts = {"citation_and_text": 0, "citation_only": 0, "text_only": 0, "none": 0}
    total_score = 0.0

    for claim in claims or []:
        row = dict(claim)
        verification = find_supporting_evidence_for_claim(row, evidence_chunks or [], references or [])
        support_type = str(verification.get("support_type") or "none")
        support_type_counts[support_type] = support_type_counts.get(support_type, 0) + 1
        score = float(verification.get("best_score") or 0.0)
        total_score += score
        text = str(row.get("claim") or row.get("text") or "")
        if row.get("contains_unverified") or "未確認" in text:
            status = "unresolved"
            unresolved += 1
        elif support_type in {"citation_and_text", "text_only"}:
            status = "supported"
            supported += 1
        elif support_type == "citation_only":
            status = "weakly_supported"
            weakly_supported += 1
        else:
            status = "unsupported"
            unsupported += 1

        best_evidence = verification.get("best_evidence") if isinstance(verification.get("best_evidence"), dict) else None
        row.update(
            {
                "status": status,
                "support_score": score,
                "support_type": support_type,
                "supporting_source_ids": list(verification.get("supporting_source_ids") or []),
                "matched_evidence_count": int(verification.get("matched_evidence_count") or 0),
                "best_evidence_title": _best_title(best_evidence),
                "best_evidence_citation_label": _normalize_citation_label((best_evidence or {}).get("citation_label") or (best_evidence or {}).get("label")),
            }
        )
        evaluated.append(row)

    claim_count = len(claims or [])
    return {
        "claims": evaluated,
        "supported_claim_count": supported,
        "weakly_supported_claim_count": weakly_supported,
        "unsupported_claim_count": unsupported,
        "unresolved_claim_count": unresolved,
        "average_support_score": (total_score / claim_count) if claim_count else 0.0,
        "support_type_counts": support_type_counts,
    }


def _clean_line(line: str) -> str:
    text = _HEADING_RE.sub("", line.strip())
    text = _BULLET_RE.sub("", text).strip()
    return text


def _is_excluded(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True
    if lowered in {"references", "reference", "sources", "evidence"}:
        return True
    if lowered.startswith(("## references", "## sources", "## evidence")):
        return True
    if text.strip() in {"結論", "調査目的", "不確実性", "追加確認が必要な点", "References", "Sources"}:
        return True
    return False



def extract_unresolved_section_items(answer_text: str) -> list[str]:
    """Return bullet/text items under the follow-up-needed section without treating them as claims."""
    items: list[str] = []
    in_section = False
    for raw_line in str(answer_text or "").splitlines():
        stripped = raw_line.strip()
        if re.match(r"^#{1,6}\s*追加確認が必要な点\s*$", stripped):
            in_section = True
            continue
        if in_section and re.match(r"^#{1,6}\s+", stripped):
            break
        if not in_section:
            continue
        text = _clean_line(stripped)
        if text and not _is_excluded(text):
            items.append(text)
    return items

def extract_claim_candidates(answer_text: str) -> list[dict[str, Any]]:
    """Extract lightweight claim candidates without invoking an LLM."""
    candidates: list[dict[str, Any]] = []
    in_references = False
    in_unresolved_section = False
    for raw_line in str(answer_text or "").splitlines():
        stripped = raw_line.strip()
        if re.match(r"^#{1,6}\s*(References|Sources|参考|出典)\b", stripped, re.IGNORECASE):
            in_references = True
            continue
        if re.match(r"^#{1,6}\s*追加確認が必要な点\s*$", stripped):
            in_unresolved_section = True
            continue
        if in_unresolved_section and re.match(r"^#{1,6}\s+", stripped):
            in_unresolved_section = False
        if in_references or in_unresolved_section:
            continue
        text = _clean_line(stripped)
        if _is_excluded(text):
            continue
        parts = [p.strip() for p in re.split(r"(?<=[。.!?！？])\s+", text) if p.strip()] or [text]
        for part in parts:
            if _is_excluded(part) or len(part) < 8:
                continue
            citations = _CITATION_RE.findall(part)
            candidates.append(
                {
                    "claim": part,
                    "text": part,
                    "citations": [f"[{label}]" for label in citations],
                    "has_citation": bool(citations),
                    "contains_unverified": "未確認" in part,
                    "status": "unresolved" if "未確認" in part else "candidate",
                }
            )
            if len(candidates) >= 30:
                return candidates
    return candidates


def _reference_labels(references: list[dict[str, Any]], evidence_chunks: list[dict[str, Any]]) -> set[str]:
    labels: set[str] = set()
    for row in list(references or []) + list(evidence_chunks or []):
        if not isinstance(row, dict):
            continue
        raw = str(row.get("citation_label") or row.get("label") or "").strip()
        if raw:
            labels.add(raw if raw.startswith("[") else f"[{raw}]")
    return labels


def _source_ids(rows: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict) and row.get("source_id"):
            ids.add(str(row.get("source_id")))
    return ids


def evaluate_claim_support(
    claims: list[dict[str, Any]], evidence_chunks: list[dict[str, Any]], references: list[dict[str, Any]]
) -> dict[str, Any]:
    source_ids = _source_ids(evidence_chunks) or _source_ids(references)
    support = verify_claim_support(claims, evidence_chunks, references)
    return {
        **support,
        "weak_evidence": not bool(evidence_chunks),
        "low_diversity": bool(evidence_chunks) and len(source_ids) <= 1,
    }


def analyze_claim_level_gaps(answer_payload: dict, evidence_chunks: list[dict], sources: list[dict]) -> dict[str, Any]:
    answer_text = str(
        (answer_payload or {}).get("answer_markdown")
        or (answer_payload or {}).get("answer")
        or (answer_payload or {}).get("summary")
        or ""
    )
    references = list((answer_payload or {}).get("references") or sources or [])
    claims = extract_claim_candidates(answer_text)
    section_unresolved_items = extract_unresolved_section_items(answer_text)
    support = evaluate_claim_support(claims, evidence_chunks or [], references)
    evaluated_claims = list(support.get("claims") or [])
    for row in evaluated_claims:
        quality_summary = summarize_supporting_source_quality(row, sources or [], evidence_chunks or [], references)
        row["source_quality_summary"] = quality_summary
        status = str(row.get("status") or "")
        if status == "unresolved":
            row["quality_adjusted_status"] = "unresolved"
        elif status == "supported" and quality_summary.get("low_quality_source_count") and not quality_summary.get("high_quality_source_count") and float(quality_summary.get("best_quality_score") or 0.0) < 0.45:
            row["quality_adjusted_status"] = "weakly_supported"
        elif status == "weakly_supported" and quality_summary.get("low_quality_source_count") and not quality_summary.get("high_quality_source_count"):
            row["quality_adjusted_status"] = "unsupported"
        else:
            row["quality_adjusted_status"] = status
    support["claims"] = evaluated_claims
    claim_count = len(claims)
    supported_count = int(support["supported_claim_count"])
    weakly_supported_count = int(support["weakly_supported_claim_count"])
    unsupported_count = int(support["unsupported_claim_count"])
    unresolved_count = int(support["unresolved_claim_count"])
    supported_quality_scores = [
        float((row.get("source_quality_summary") or {}).get("average_quality_score") or 0.0)
        for row in evaluated_claims
        if row.get("status") in {"supported", "weakly_supported"}
        and float((row.get("source_quality_summary") or {}).get("average_quality_score") or 0.0) > 0
    ]
    average_source_quality_score = (sum(supported_quality_scores) / len(supported_quality_scores)) if supported_quality_scores else 0.0
    high_quality_supported_claim_count = sum(
        1 for row in evaluated_claims if row.get("status") == "supported" and (row.get("source_quality_summary") or {}).get("high_quality_source_count")
    )
    low_quality_supported_claim_count = sum(
        1
        for row in evaluated_claims
        if row.get("status") in {"supported", "weakly_supported"}
        and (row.get("source_quality_summary") or {}).get("low_quality_source_count")
        and not (row.get("source_quality_summary") or {}).get("high_quality_source_count")
    )
    source_quality_warnings = []
    if low_quality_supported_claim_count:
        source_quality_warnings.append(f"supported_by_low_quality_sources={low_quality_supported_claim_count}")
    gaps: list[str] = []
    if claim_count == 0:
        gaps.append("no_claims_extracted")
    if weakly_supported_count:
        gaps.append("weakly_supported_claims")
    if unsupported_count:
        gaps.append("unsupported_claims")
    if unresolved_count:
        gaps.append("unresolved_claims")
    if support.get("low_diversity"):
        gaps.append("low_evidence_diversity")
    if low_quality_supported_claim_count:
        gaps.append("supported_by_low_quality_sources")
    low_quality_source_count = sum(1 for item in build_source_quality_index(sources or [], evidence_chunks or [], references).values() if item.get("quality_level") == "low")
    if low_quality_source_count:
        gaps.append("low_quality_sources")
    contradiction_result = detect_claim_contradictions(evaluated_claims, evidence_chunks or [], references)
    contradiction_count = int(contradiction_result.get("contradiction_count") or 0)
    contradictions = list(contradiction_result.get("contradictions") or [])
    if contradiction_count:
        gaps.append("possible_contradictions")
    support_ratio = (supported_count / claim_count) if claim_count else 0.0
    confidence_adjustment = (
        min(0.20, support_ratio * 0.20)
        - min(0.12, weakly_supported_count * 0.02)
        - min(0.20, unsupported_count * 0.03)
        - min(0.10, unresolved_count * 0.02)
    )
    confidence_adjustment += min(0.08, average_source_quality_score * 0.08)
    confidence_adjustment -= min(0.12, low_quality_supported_claim_count * 0.03)
    confidence_adjustment -= min(0.12, contradiction_count * 0.03)
    if any(str(item.get("severity")) == "high" for item in contradictions):
        confidence_adjustment -= 0.06
    return {
        "claim_count": claim_count,
        "supported_claim_count": supported_count,
        "weakly_supported_claim_count": weakly_supported_count,
        "unsupported_claim_count": unsupported_count,
        "unresolved_claim_count": unresolved_count,
        "low_diversity": bool(support.get("low_diversity")),
        "high_quality_supported_claim_count": high_quality_supported_claim_count,
        "low_quality_supported_claim_count": low_quality_supported_claim_count,
        "average_source_quality_score": float(average_source_quality_score),
        "source_quality_warnings": source_quality_warnings,
        "contradiction_count": contradiction_count,
        "contradictions": contradictions,
        "gaps": gaps,
        "unresolved_items": [
            *[c.get("claim") or c.get("text") for c in support["claims"] if c.get("status") == "unresolved"],
            *section_unresolved_items,
        ],
        "support_ratio": support_ratio,
        "confidence_adjustment": confidence_adjustment,
        "average_support_score": float(support.get("average_support_score") or 0.0),
        "support_type_counts": dict(support.get("support_type_counts") or {}),
        "claims": support["claims"],
    }
