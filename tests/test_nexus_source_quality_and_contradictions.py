import json
import uuid
from pathlib import Path

from app.nexus.db import get_conn
from app.nexus.jobs import create_job
from app.nexus.report import BuildReportRequest, build_job_report
from app.nexus.research_gaps import (
    analyze_claim_level_gaps,
    detect_claim_contradictions,
    score_source_quality,
    verify_claim_support,
)


def test_official_pdf_scores_high():
    result = score_source_quality(
        {
            "source_id": "s1",
            "domain": "meti.go.jp",
            "content_type": "application/pdf",
            "is_official": True,
            "status": "downloaded",
            "quote": "経済産業省の公式レポート本文です。十分な長さの説明を含みます。",
        }
    )
    assert result["quality_level"] == "high"
    assert result["quality_score"] >= 0.75


def test_degraded_unknown_scores_low():
    result = score_source_quality({"source_id": "s1", "status": "degraded", "content_type": "", "quote": "短文"})
    assert result["quality_level"] == "low"
    assert result["quality_score"] < 0.45


def test_supported_claim_gets_source_quality_summary():
    result = verify_claim_support(
        [{"claim": "2026年に量産開始します [S1]", "text": "2026年に量産開始します [S1]", "citations": ["[S1]"]}],
        [{"source_id": "s1", "citation_label": "[S1]", "quote": "2026年に量産開始します"}],
        [],
    )
    analysis = analyze_claim_level_gaps(
        {"answer_markdown": "2026年に量産開始します [S1]", "references": [{"source_id": "s1", "citation_label": "[S1]"}]},
        [{"source_id": "s1", "citation_label": "[S1]", "quote": "2026年に量産開始します"}],
        [
            {
                "source_id": "s1",
                "domain": "meti.go.jp",
                "content_type": "application/pdf",
                "is_official": True,
                "status": "downloaded",
                "quote": "2026年に量産開始します。公式PDFレポート本文です。",
            }
        ],
    )
    assert result["claims"][0]["status"] == "supported"
    summary = analysis["claims"][0]["source_quality_summary"]
    assert summary["best_quality_score"] >= 0.75
    assert summary["high_quality_source_count"] == 1


def test_supported_by_low_quality_sources_adds_gap():
    analysis = analyze_claim_level_gaps(
        {"answer_markdown": "2026年に量産開始します [S1]", "references": [{"source_id": "s1", "citation_label": "[S1]"}]},
        [{"source_id": "s1", "citation_label": "[S1]", "quote": "2026年に量産開始します"}],
        [{"source_id": "s1", "status": "degraded", "content_type": "", "quote": "短文"}],
    )
    assert {"supported_by_low_quality_sources", "low_quality_sources"} & set(analysis["gaps"])
    assert analysis["low_quality_supported_claim_count"] >= 1


def test_detect_year_mismatch_contradiction():
    claims = [
        {
            "claim": "2026年に量産開始",
            "text": "2026年に量産開始",
            "supporting_source_ids": ["s1", "s2"],
            "status": "supported",
        }
    ]
    result = detect_claim_contradictions(
        claims,
        [
            {"source_id": "s1", "quote": "2026年に量産開始"},
            {"source_id": "s2", "quote": "2027年以降に延期"},
        ],
        [],
    )
    assert result["contradiction_count"] >= 1
    assert result["contradictions"][0]["type"] == "year_mismatch"


def test_detect_negation_conflict():
    claims = [{"claim": "採用が決定しています", "text": "採用が決定しています", "supporting_source_ids": ["s1"]}]
    result = detect_claim_contradictions(claims, [{"source_id": "s1", "quote": "採用は未定"}], [])
    assert result["contradiction_count"] >= 1
    assert result["contradictions"][0]["type"] in {"negation_conflict", "modal_uncertainty"}


def test_report_metadata_contains_quality_and_contradiction_summary():
    job_id = f"job-quality-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="report", status="completed", message="done")
    claim_analysis = {
        "claim_count": 1,
        "supported_claim_count": 1,
        "weakly_supported_claim_count": 0,
        "unsupported_claim_count": 0,
        "unresolved_claim_count": 0,
        "average_source_quality_score": 0.22,
        "high_quality_supported_claim_count": 0,
        "low_quality_supported_claim_count": 1,
        "contradiction_count": 1,
        "source_quality_warnings": ["supported_by_low_quality_sources=1"],
        "contradictions": [{"claim": "2026年に量産開始", "type": "year_mismatch", "severity": "medium"}],
        "gaps": ["supported_by_low_quality_sources", "possible_contradictions"],
        "claims": [{"claim": "2026年に量産開始 [S1]", "status": "supported", "citations": ["[S1]"]}],
    }
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
                "# 回答\n2026年に量産開始 [S1]",
                "[]",
                json.dumps({"question": "調査質問", "answer_markdown": "2026年に量産開始 [S1]", "claim_analysis": claim_analysis}, ensure_ascii=False),
                "[]",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()

    report = build_job_report(BuildReportRequest(job_id=job_id, report_type="deep_research", title="Deep Report"))
    data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    metadata = data["metadata"]["claim_analysis"]
    assert metadata["average_source_quality_score"] == 0.22
    assert metadata["low_quality_supported_claim_count"] == 1
    assert metadata["contradiction_count"] == 1
    assert metadata["contradictions"][0]["type"] == "year_mismatch"
    uncertainty = next(section["summary"] for section in data["sections"] if section["heading"] == "不確実性")
    assert "low_quality_supported_claims=1" in uncertainty
    assert "possible_contradictions=1" in uncertainty
