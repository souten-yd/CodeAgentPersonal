import json
import uuid
from pathlib import Path

from app.nexus.db import get_conn
from app.nexus.jobs import create_job
from app.nexus.report import BuildReportRequest, build_job_report


def _insert_answer(job_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nexus_research_answers(
                answer_id, job_id, project, question, answer_markdown,
                evidence_json, answer_json, source_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"answer-{uuid.uuid4().hex[:8]}",
                job_id,
                "default",
                "調査質問",
                "# 回答\n結論本文 [S1]",
                "[]",
                json.dumps(
                    {
                        "question": "調査質問",
                        "answer_markdown": "# 回答\n結論本文 [S1]",
                        "references": [{"citation_label": "[S1]", "url": "https://example.com"}],
                        "claim_analysis": {
                            "claim_count": 1,
                            "supported_claim_count": 1,
                            "unsupported_claim_count": 0,
                            "unresolved_claim_count": 0,
                            "gaps": [],
                            "claims": [{"claim": "結論本文 [S1]", "status": "supported", "citations": ["[S1]"]}],
                        },
                    },
                    ensure_ascii=False,
                ),
                "[]",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_report_uses_latest_research_answer_when_available():
    job_id = f"job-report-answer-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="report", status="completed", message="done")
    _insert_answer(job_id)

    report = build_job_report(BuildReportRequest(job_id=job_id, report_type="deep_research", title="Deep Report"))

    assert report["markdown_path"] == report["report_md_path"]
    assert report["json_path"] == report["report_json_path"]
    assert report["html_path"] == report["report_html_path"]
    assert Path(report["markdown_path"]).exists()
    assert Path(report["json_path"]).exists()
    assert Path(report["html_path"]).exists()
    data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "research_answer"
    headings = [section["heading"] for section in data["sections"]]
    assert "主要主張と根拠" in headings
    markdown = Path(report["markdown_path"]).read_text(encoding="utf-8")
    assert "結論本文" in markdown
    assert "supported" in markdown


def test_report_falls_back_to_evidence_only_without_answer():
    job_id = f"job-report-fallback-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="report", status="completed", message="done")

    report = build_job_report(BuildReportRequest(job_id=job_id, report_type="general"))

    data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "evidence_only"
    assert {"markdown_path", "json_path", "html_path", "report_md_path", "report_json_path", "report_html_path"} <= set(report)
