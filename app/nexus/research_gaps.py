from __future__ import annotations

import re
from typing import Any

_CITATION_RE = re.compile(r"\[(S\d+)\]")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+")


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
    labels = _reference_labels(references, evidence_chunks)
    source_ids = _source_ids(evidence_chunks) or _source_ids(references)
    evaluated: list[dict[str, Any]] = []
    supported = unsupported = unresolved = 0
    for claim in claims or []:
        row = dict(claim)
        citations = list(row.get("citations") or [])
        if row.get("contains_unverified") or "未確認" in str(row.get("claim") or row.get("text") or ""):
            status = "unresolved"
            unresolved += 1
        elif citations and any(label in labels for label in citations):
            status = "supported"
            supported += 1
        else:
            status = "unsupported"
            unsupported += 1
        row["status"] = status
        evaluated.append(row)
    return {
        "claims": evaluated,
        "supported_claim_count": supported,
        "unsupported_claim_count": unsupported,
        "unresolved_claim_count": unresolved,
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
    unsupported_count = int(support["unsupported_claim_count"])
    unresolved_count = int(support["unresolved_claim_count"])
    gaps: list[str] = []
    if claim_count == 0:
        gaps.append("no_claims_extracted")
    if unsupported_count:
        gaps.append("unsupported_claims")
    if unresolved_count:
        gaps.append("unresolved_claims")
    if support.get("low_diversity"):
        gaps.append("low_evidence_diversity")
    support_ratio = (supported_count / claim_count) if claim_count else 0.0
    confidence_adjustment = min(0.20, support_ratio * 0.20) - min(0.20, unsupported_count * 0.03) - min(0.10, unresolved_count * 0.02)
    return {
        "claim_count": claim_count,
        "supported_claim_count": supported_count,
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
        "claims": support["claims"],
    }
