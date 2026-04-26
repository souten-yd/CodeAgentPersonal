from __future__ import annotations


def build_answer_payload(*, question: str, summary: str, references: list[dict]) -> dict:
    markdown_lines = [f"## Answer\n\n{summary}", "", "## References"]
    for ref in references:
        label = str(ref.get("citation_label") or "[?]")
        title = str(ref.get("title") or ref.get("source_url") or "(untitled)")
        url = str(ref.get("source_url") or "")
        markdown_lines.append(f"- {label} {title} ({url})" if url else f"- {label} {title}")

    return {
        "question": question,
        "answer": summary,
        "answer_markdown": "\n".join(markdown_lines).strip(),
        "references": references,
    }
