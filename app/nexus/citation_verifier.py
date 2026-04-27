from __future__ import annotations

import re

_VALID_LABEL_PATTERN = re.compile(r"\[S([1-9]\d*)\]")
_BRACKET_TOKEN_PATTERN = re.compile(r"\[[^\[\]\n]{1,32}\]")


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


def verify_citation_labels(*, answer_text: str, references: list[dict]) -> dict:
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

    return {
        "ok": not missing_in_references and not unused_references and not invalid_labels,
        "missing_in_references": missing_in_references,
        "unused_references": unused_references,
        "invalid_labels": invalid_labels,
    }
