from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.nexus.db import NEXUS_DIR, get_conn, transaction
from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import get_job

nexus_report_router = APIRouter()


REPORTS_DIR = NEXUS_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _safe_quote(text: str | None, max_len: int = 200) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1] + "…"



def build_report(job_id: str, report_type: str, title: str, sections: list[dict]) -> dict:
    """Generate report.md + report.json (+ optional HTML) using standard template."""
    if not job_id:
        raise ValueError("job_id is required")
    if not report_type:
        raise ValueError("report_type is required")

    report_id = str(uuid.uuid4())
    report_dir = REPORTS_DIR / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    generated_at = _now_iso()
    md_lines = [
        f"# {title}",
        "",
        "## Report Metadata",
        f"- job_id: {job_id}",
        f"- report_id: {report_id}",
        f"- report_type: {report_type}",
        f"- generated_at: {generated_at}",
        "",
        "> 著作権保護のため本文の全文転載は避け、必要最小限の要約と citation_label を中心に記載しています。",
        "",
    ]

    normalized_sections: list[dict] = []
    for idx, section in enumerate(sections, start=1):
        heading = section.get("heading") or f"Section {idx}"
        summary = section.get("summary") or ""
        evidence = section.get("evidence") or []

        md_lines.append(f"## {heading}")
        if summary:
            md_lines.append(summary)
            md_lines.append("")

        if evidence:
            md_lines.append("### Evidence")
            for ev in evidence:
                citation_label = ev.get("citation_label") or "[citation missing]"
                source_url = ev.get("source_url") or ""
                retrieved_at = ev.get("retrieved_at") or ""
                quote = _safe_quote(ev.get("quote"))
                row = f"- {citation_label}"
                if source_url:
                    row += f" ({source_url})"
                if retrieved_at:
                    row += f" retrieved_at={retrieved_at}"
                md_lines.append(row)
                if quote:
                    md_lines.append(f"  - 引用（抜粋）: {quote}")
        md_lines.append("")

        normalized_sections.append(
            {
                "heading": heading,
                "summary": summary,
                "evidence": [
                    {
                        "citation_label": ev.get("citation_label"),
                        "source_url": ev.get("source_url"),
                        "retrieved_at": ev.get("retrieved_at"),
                        "quote": _safe_quote(ev.get("quote")),
                        "note": ev.get("note"),
                    }
                    for ev in evidence
                ],
            }
        )

    report_json = {
        "report_id": report_id,
        "job_id": job_id,
        "report_type": report_type,
        "title": title,
        "generated_at": generated_at,
        "sections": normalized_sections,
    }

    report_md_path = report_dir / "report.md"
    report_json_path = report_dir / "report.json"
    report_html_path = report_dir / "report.html"

    report_md_path.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")
    report_json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")

    html_body = [f"<h1>{html.escape(title)}</h1>", "<ul>"]
    html_body.extend(
        [
            f"<li>job_id: {html.escape(job_id)}</li>",
            f"<li>report_id: {html.escape(report_id)}</li>",
            f"<li>report_type: {html.escape(report_type)}</li>",
            f"<li>generated_at: {html.escape(generated_at)}</li>",
        ]
    )
    html_body.append("</ul>")
    for section in normalized_sections:
        html_body.append(f"<h2>{html.escape(section['heading'])}</h2>")
        if section["summary"]:
            html_body.append(f"<p>{html.escape(section['summary'])}</p>")
        if section["evidence"]:
            html_body.append("<ul>")
            for ev in section["evidence"]:
                citation = html.escape(ev.get("citation_label") or "[citation missing]")
                url = html.escape(ev.get("source_url") or "")
                rt = html.escape(ev.get("retrieved_at") or "")
                html_body.append(f"<li>{citation} {url} {rt}</li>")
            html_body.append("</ul>")

    report_html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + html.escape(title)
        + "</title></head><body>"
        + "".join(html_body)
        + "</body></html>",
        encoding="utf-8",
    )

    return {
        "report_id": report_id,
        "job_id": job_id,
        "report_type": report_type,
        "title": title,
        "report_dir": str(report_dir),
        "report_md_path": str(report_md_path),
        "report_json_path": str(report_json_path),
        "report_html_path": str(report_html_path),
        "generated_at": generated_at,
    }


def save_report_record(report: dict) -> None:
    created_at = _now_iso()
    project = str(report.get("project") or "default")
    with transaction() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO nexus_reports(
                report_id, project, job_id, report_type, title, report_dir,
                report_md_path, report_json_path, report_html_path,
                summary, metadata, generated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["report_id"],
                project,
                report["job_id"],
                report["report_type"],
                report["title"],
                report["report_dir"],
                report["report_md_path"],
                report["report_json_path"],
                report["report_html_path"],
                str(report.get("summary") or ""),
                "{}",
                report["generated_at"],
                created_at,
            ),
        )


def get_latest_report(job_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                report_id, project, job_id, report_type, title, report_dir,
                report_md_path, report_json_path, report_html_path,
                summary, metadata, generated_at, created_at
            FROM nexus_reports
            WHERE job_id = ?
            ORDER BY generated_at DESC, created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def _build_sections_from_evidence(evidence_items: list[dict]) -> list[dict]:
    if not evidence_items:
        return [
            {
                "heading": "Evidence",
                "summary": "No evidence was found for this job.",
                "evidence": [],
            }
        ]

    return [
        {
            "heading": "Evidence",
            "summary": f"Collected evidence count: {len(evidence_items)}",
            "evidence": evidence_items,
        }
    ]


class BuildReportRequest(BaseModel):
    job_id: str = Field(min_length=1)
    report_type: str = Field(default="general", min_length=1)
    title: str | None = None


@nexus_report_router.post("/report/build")
def build_job_report(payload: BuildReportRequest) -> dict:
    job = get_job(payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    evidence_items = list_evidence_items(payload.job_id)
    sections = _build_sections_from_evidence(evidence_items)
    title = payload.title or f"Nexus Report ({payload.job_id})"

    report = build_report(
        job_id=payload.job_id,
        report_type=payload.report_type,
        title=title,
        sections=sections,
    )
    report["project"] = "default"
    save_report_record(report)
    return report
