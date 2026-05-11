from __future__ import annotations

import re
from typing import Any

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
    claim_count = len(claims)
    supported_count = int(support["supported_claim_count"])
    weakly_supported_count = int(support["weakly_supported_claim_count"])
    unsupported_count = int(support["unsupported_claim_count"])
    unresolved_count = int(support["unresolved_claim_count"])
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
    support_ratio = (supported_count / claim_count) if claim_count else 0.0
    confidence_adjustment = (
        min(0.20, support_ratio * 0.20)
        - min(0.12, weakly_supported_count * 0.02)
        - min(0.20, unsupported_count * 0.03)
        - min(0.10, unresolved_count * 0.02)
    )
    return {
        "claim_count": claim_count,
        "supported_claim_count": supported_count,
        "weakly_supported_claim_count": weakly_supported_count,
        "unsupported_claim_count": unsupported_count,
        "unresolved_claim_count": unresolved_count,
        "low_diversity": bool(support.get("low_diversity")),
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
