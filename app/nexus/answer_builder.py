from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from app.nexus.config import NEXUS_PATHS
from app.nexus.db import transaction
from app.nexus.utils import ensure_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_answer_markdown(*, question: str, summary: str, references: list[dict]) -> str:
    markdown_lines = [f"# Answer", "", f"## Question", question, "", "## Answer", summary, "", "## References"]
    for idx, ref in enumerate(references, start=1):
        label = str(ref.get("citation_label") or f"[S{idx}]")
        title = str(ref.get("title") or ref.get("url") or "(untitled)")
        url = str(ref.get("url") or "")
        local_path = str(ref.get("local_path") or "")
        line = f"- {label} {title}"
        if url:
            line += f" ({url})"
        elif local_path:
            line += f" ({local_path})"
        markdown_lines.append(line)
    return "\n".join(markdown_lines).strip() + "\n"


def _job_answer_dir(job_id: str) -> Path:
    return ensure_dir(NEXUS_PATHS.nexus_dir / "research_jobs" / job_id)


def _write_answer_files(*, job_id: str, answer_markdown: str, answer_json: dict) -> dict:
    out_dir = _job_answer_dir(job_id)
    md_path = out_dir / "answer.md"
    json_path = out_dir / "answer.json"
    md_path.write_text(answer_markdown, encoding="utf-8")
    json_path.write_text(json.dumps(answer_json, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "answer_md_path": str(md_path),
        "answer_json_path": str(json_path),
    }


def _save_answer_row(
    *,
    job_id: str,
    project: str,
    question: str,
    answer_markdown: str,
    evidence_json: list[dict],
    references: list[dict],
) -> str:
    answer_id = str(uuid.uuid4())
    created_at = _now_iso()
    source_ids: list[str] = []
    seen: set[str] = set()
    for ref in references:
        source_id = str(ref.get("source_id") or "").strip()
        if source_id and source_id not in seen:
            seen.add(source_id)
            source_ids.append(source_id)

    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO nexus_research_answers(
                answer_id, job_id, project, question,
                answer_markdown, evidence_json, source_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                job_id,
                project,
                question,
                answer_markdown,
                json.dumps(evidence_json, ensure_ascii=False),
                json.dumps(source_ids, ensure_ascii=False),
                created_at,
            ),
        )
    return answer_id


def build_answer_payload(
    *,
    question: str,
    references: list[dict],
    summary: str | None = None,
    evidence: list[dict] | None = None,
    job_id: str | None = None,
    project: str = "default",
) -> dict:
    summary_text = (summary or "").strip() or f"{question} に関する調査結果を整理しました。"
    if references:
        citation_tokens = " ".join(f"[S{idx}]" for idx, _ in enumerate(references, start=1))
        if not any(f"[S{idx}]" in summary_text for idx, _ in enumerate(references, start=1)):
            summary_text = f"{summary_text} {citation_tokens}".strip()
    else:
        summary_text = f"{summary_text} 未確認のため断定は避けます。".strip()
    evidence_json = evidence if evidence is not None else references

    answer_markdown = _build_answer_markdown(
        question=question,
        summary=summary_text,
        references=references,
    )
    payload = {
        "question": question,
        "answer": summary_text,
        "answer_markdown": answer_markdown,
        "evidence_json": evidence_json,
        "references": references,
    }

    if job_id:
        paths = _write_answer_files(job_id=job_id, answer_markdown=answer_markdown, answer_json=payload)
        answer_id = _save_answer_row(
            job_id=job_id,
            project=project,
            question=question,
            answer_markdown=answer_markdown,
            evidence_json=evidence_json,
            references=references,
        )
        payload.update(paths)
        payload["answer_id"] = answer_id

    return payload
