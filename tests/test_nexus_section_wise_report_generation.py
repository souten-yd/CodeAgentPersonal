import json
import uuid
from pathlib import Path

from app.nexus.db import get_conn
from app.nexus.jobs import create_job
from app.nexus.report import BuildReportRequest, build_job_report


def _insert_market_answer(job_id: str) -> None:
    evidence = [
        {
            "citation_label": "[S1]",
            "url": "https://example.org/market.pdf",
            "title": "航空機電動化 market size forecast report",
            "quote": "市場規模は電動推進、充電インフラ、地域別需要の伸びに左右され、2030年代にかけて段階的な成長が予測される。",
        },
        {
            "citation_label": "[S2]",
            "url": "https://example.com/players",
            "title": "Key players and OEM supplier partnerships",
            "quote": "主要企業はOEM、バッテリーサプライヤー、航空機メーカーの提携を通じて実証機と量産準備を進めている。",
        },
        {
            "citation_label": "[S3]",
            "url": "https://example.gov/policy",
            "title": "Government regulation certification policy",
            "quote": "規制当局は安全認証、騒音基準、運航ルールを段階的に整備しており、商用化時期に影響する。",
        },
        {
            "citation_label": "[S4]",
            "url": "https://example.net/risk",
            "title": "Battery safety risk bottleneck",
            "quote": "バッテリー安全性、重量、供給制約、空港インフラ整備の遅れは導入ペースを制約するリスクである。",
        },
    ]
    coverage_matrix = [
        {"dimension": "market_size", "status": "covered", "evidence_count": 3, "best_sources": ["[S1]"], "notes": "十分な根拠があります。"},
        {"dimension": "key_players", "status": "covered", "evidence_count": 3, "best_sources": ["[S2]"], "notes": "十分な根拠があります。"},
        {"dimension": "technology_trends", "status": "weak", "evidence_count": 1, "best_sources": ["[S1]"], "notes": "根拠が限定的です。"},
        {"dimension": "regulation", "status": "covered", "evidence_count": 3, "best_sources": ["[S3]"], "notes": "十分な根拠があります。"},
        {"dimension": "investment", "status": "missing", "evidence_count": 0, "best_sources": [], "notes": "該当根拠が不足しています。"},
        {"dimension": "risks", "status": "weak", "evidence_count": 1, "best_sources": ["[S4]"], "notes": "根拠が限定的です。"},
        {"dimension": "timeline", "status": "missing", "evidence_count": 0, "best_sources": [], "notes": "該当根拠が不足しています。"},
    ]
    answer_json = {
        "question": "航空機電動化の市場動向",
        "answer_markdown": "## Answer\n航空機電動化市場は成長余地があるが、認証と供給制約が導入速度を左右する [S1] [S3]。\n\n## References\n- [S1]",
        "references": evidence,
        "evidence_json": evidence,
        "report_outline": [
            "Executive Summary",
            "市場概況",
            "主要ドライバー",
            "技術動向",
            "主要プレイヤー",
            "政策・規制",
            "投資・提携",
            "リスク・制約",
            "今後12〜36か月の見通し",
            "根拠と不確実性",
            "追加調査項目",
        ],
        "coverage_matrix": coverage_matrix,
        "retrieval_summary": {
            "candidate_count": 20,
            "valid_source_count": 4,
            "evidence_count": 4,
            "focused_research_plan": {
                "must_cover_dimensions": ["market_size", "key_players", "technology_trends", "regulation", "investment", "risks", "timeline"],
                "focused_queries": [],
            },
            "coverage_matrix": coverage_matrix,
            "source_mix": {"official": 1, "report_pdf": 1, "company_ir": 1},
        },
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
                answer_json["question"],
                answer_json["answer_markdown"],
                json.dumps(evidence, ensure_ascii=False),
                json.dumps(answer_json, ensure_ascii=False),
                "[]",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_section_mapping_and_evidence_assignment_from_planner_outline():
    job_id = f"job-section-report-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="market", status="completed", message="done")
    _insert_market_answer(job_id)

    report = build_job_report(BuildReportRequest(job_id=job_id, report_type="deep_research", title="Market Report"))
    data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))

    section_coverage = data["metadata"]["section_coverage"]
    market_overview = next(item for item in section_coverage if item["heading"] == "市場概況")
    assert market_overview["dimensions"] == ["market_size"]
    assert market_overview["evidence_count"] >= 1
    players = next(section for section in data["sections"] if section["heading"] == "主要プレイヤー")
    assert players["evidence"]
    assert "[S2]" in {ev["citation_label"] for ev in players["evidence"]}


def test_market_analysis_sections_are_substantive_and_include_uncertainty():
    job_id = f"job-market-report-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="market", status="completed", message="done")
    _insert_market_answer(job_id)

    report = build_job_report(BuildReportRequest(job_id=job_id, report_type="market_analysis", title="Market Report"))
    data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(report["markdown_path"]).read_text(encoding="utf-8")
    headings = [section["heading"] for section in data["sections"]]

    for heading in ["市場概況", "主要プレイヤー", "政策・規制", "リスク・制約"]:
        assert heading in headings
        section = next(item for item in data["sections"] if item["heading"] == heading)
        assert len(section["summary"]) >= 250
        assert section["summary"].strip() not in {"[S1]", "[S2]", "[S3]", "[S4]"}
    assert "不確実性" in markdown
    assert "investment" in markdown or "投資・提携はmissing" in markdown


def test_llm_unavailable_uses_deterministic_section_summary():
    job_id = f"job-deterministic-report-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="market", status="completed", message="done")
    _insert_market_answer(job_id)

    report = build_job_report(BuildReportRequest(job_id=job_id, report_type="market_analysis", title="Market Report"))
    data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))

    executive = next(item for item in data["metadata"]["section_coverage"] if item["heading"] == "Executive Summary")
    assert executive["generation"]["mode"] == "deterministic"
    assert executive["generation"]["reason"] in {"section_llm_disabled_or_no_evidence"} or executive["generation"]["reason"].startswith("section_llm_")
