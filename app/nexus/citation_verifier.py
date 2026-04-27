from __future__ import annotations

import re
from typing import Literal

_VALID_LABEL_PATTERN = re.compile(r"\[S([1-9]\d*)\]")
_BRACKET_TOKEN_PATTERN = re.compile(r"\[[^\[\]\n]{1,32}\]")
_SENTENCE_PATTERN = re.compile(r"[^。．.!?！？\n]+(?:[。．.!?！？](?:\s*\[S[1-9]\d*\])*)?|\[S[1-9]\d*\]")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9一-龥ぁ-んァ-ンー]{2,}")

SentenceSupport = Literal["supported", "weak", "unsupported"]


def extract_citation_labels(answer_text: str) -> tuple[list[str], list[str]]:
    """Extract [S1] style citation labels from answer text.

    Returns a tuple: (valid_labels, invalid_labels).
    invalid_labels includes bracket tokens that look citation-related but are not
    in the strict [S<number>] format.
    """

    text = str(answer_text or "")
    valid_labels = [f"[S{match.group(1)}]" for match in _VALID_LABEL_PATTERN.finditer(text)]

    invalid_labels: list[str] = []
    for token in _BRACKET_TOKEN_PATTERN.findall(text):
        if token.startswith("[S") and not _VALID_LABEL_PATTERN.fullmatch(token):
            invalid_labels.append(token)

    return valid_labels, invalid_labels


def split_answer_sentences(answer_text: str) -> list[str]:
    """Split answer text into sentence-like units for citation checks."""

    text = str(answer_text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    sentences: list[str] = []
    for line in lines:
        for segment in _SENTENCE_PATTERN.findall(line):
            sentence = segment.strip()
            if sentence:
                sentences.append(sentence)
    return sentences


def _normalize_for_match(text: str) -> str:
    return _VALID_LABEL_PATTERN.sub("", str(text or "")).strip().lower()


def _tokenize(text: str) -> set[str]:
    normalized = _normalize_for_match(text)
    return {token for token in _TOKEN_PATTERN.findall(normalized)}


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    compact = re.sub(r"[\s\W_]+", "", _normalize_for_match(text))
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def _sentence_evidence_score(*, sentence: str, evidence_text: str) -> float:
    sentence_norm = _normalize_for_match(sentence)
    evidence_norm = _normalize_for_match(evidence_text)
    if not sentence_norm or not evidence_norm:
        return 0.0

    if evidence_norm in sentence_norm or sentence_norm in evidence_norm:
        return 1.0

    sentence_tokens = _tokenize(sentence_norm)
    evidence_tokens = _tokenize(evidence_norm)
    if not sentence_tokens or not evidence_tokens:
        return 0.0

    overlap = sentence_tokens & evidence_tokens
    token_score = len(overlap) / len(sentence_tokens)

    sentence_ngrams = _char_ngrams(sentence_norm)
    evidence_ngrams = _char_ngrams(evidence_norm)
    if not sentence_ngrams or not evidence_ngrams:
        return token_score
    ngram_overlap = sentence_ngrams & evidence_ngrams
    ngram_score = len(ngram_overlap) / len(sentence_ngrams)
    return max(token_score, ngram_score)


def _classify_support(score: float) -> SentenceSupport:
    if score >= 0.35:
        return "supported"
    if score >= 0.15:
        return "weak"
    return "unsupported"


def evaluate_sentence_citations(*, answer_text: str, evidence_chunks: list[dict] | None = None) -> dict:
    """Evaluate semantic support for each sentence based on linked citation chunks."""

    chunks = evidence_chunks or []
    if not chunks:
        sentence_results = [
            {
                "sentence_index": idx,
                "sentence": sentence,
                "citations": [f"[S{m.group(1)}]" for m in _VALID_LABEL_PATTERN.finditer(sentence)],
                "status": "weak",
                "best_score": 0.0,
                "matched_evidence": [],
            }
            for idx, sentence in enumerate(split_answer_sentences(answer_text), start=1)
        ]
        return {
            "sentence_results": sentence_results,
            "warnings": [],
        }

    chunks_by_label: dict[str, list[dict]] = {}
    for chunk in chunks:
        label = str(chunk.get("citation_label") or "").strip()
        if not label:
            continue
        chunks_by_label.setdefault(label, []).append(chunk)

    sentence_results: list[dict] = []
    warnings: list[dict] = []

    for idx, sentence in enumerate(split_answer_sentences(answer_text), start=1):
        sentence_labels = [f"[S{m.group(1)}]" for m in _VALID_LABEL_PATTERN.finditer(sentence)]
        matched_evidence: list[dict] = []
        best_score = 0.0

        if not sentence_labels:
            status: SentenceSupport = "unsupported"
            reason = "citation_missing"
        else:
            for label in sentence_labels:
                for chunk in chunks_by_label.get(label, []):
                    evidence_text = str(chunk.get("quote") or chunk.get("text") or "")
                    score = _sentence_evidence_score(sentence=sentence, evidence_text=evidence_text)
                    if score > best_score:
                        best_score = score
                    matched_evidence.append(
                        {
                            "citation_label": label,
                            "source_id": str(chunk.get("source_id") or ""),
                            "chunk_id": str(chunk.get("chunk_id") or chunk.get("id") or ""),
                            "quote": evidence_text,
                            "score": round(score, 4),
                        }
                    )

            if matched_evidence:
                status = _classify_support(best_score)
                reason = "low_semantic_overlap" if status != "supported" else "ok"
            else:
                status = "unsupported"
                reason = "citation_chunk_not_found"

        result = {
            "sentence_index": idx,
            "sentence": sentence,
            "citations": sentence_labels,
            "status": status,
            "best_score": round(best_score, 4),
            "matched_evidence": matched_evidence,
        }
        sentence_results.append(result)

        if status == "unsupported":
            warnings.append(
                {
                    "sentence_index": idx,
                    "sentence": sentence,
                    "citations": sentence_labels,
                    "reason": reason,
                }
            )

    return {
        "sentence_results": sentence_results,
        "warnings": warnings,
    }


def verify_citation_labels(*, answer_text: str, references: list[dict], evidence_chunks: list[dict] | None = None) -> dict:
    """Verify citation consistency between answer body and references."""

    used_labels, invalid_labels = extract_citation_labels(answer_text)
    used_set = set(used_labels)

    reference_labels = []
    for ref in references:
        label = str(ref.get("citation_label") or "").strip()
        if label:
            reference_labels.append(label)
    reference_set = set(reference_labels)

    missing_in_references = sorted(used_set - reference_set)
    unused_references = sorted(reference_set - used_set)

    semantic = evaluate_sentence_citations(answer_text=answer_text, evidence_chunks=evidence_chunks)

    return {
        "ok": not missing_in_references and not unused_references and not invalid_labels and not semantic["warnings"],
        "missing_in_references": missing_in_references,
        "unused_references": unused_references,
        "invalid_labels": invalid_labels,
        "sentence_results": semantic["sentence_results"],
        "warnings": semantic["warnings"],
    }
