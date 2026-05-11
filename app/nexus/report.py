from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import os
import re
from pathlib import Path
import uuid
from urllib import error, request

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.nexus.db import NEXUS_DIR, get_conn, transaction
from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import get_job

nexus_report_router = APIRouter()


REPORTS_DIR = NEXUS_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

STANDARD_CHAPTERS: tuple[str, ...] = (
    "調査目的",
    "条件",
    "結論",
    "比較",
    "不確実性",
    "Evidence",
)



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _safe_quote(text: str | None, max_len: int = 200) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1] + "…"



def build_report(job_id: str, report_type: str, title: str, sections: list[dict], metadata: dict | None = None) -> dict:
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
            display_evidence = evidence[:40] if heading.lower().startswith(("sources", "references")) else evidence
            for ev in display_evidence:
                citation_label = ev.get("citation_label") or "[citation missing]"
                source_url = ev.get("url") or ev.get("source_url") or ""
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

        normalized_section = {
            "heading": heading,
            "summary": summary,
            "evidence": [
                {
                    "citation_label": ev.get("citation_label"),
                    "source_url": ev.get("url") or ev.get("source_url"),
                    "retrieved_at": ev.get("retrieved_at"),
                    "quote": _safe_quote(ev.get("quote")),
                    "note": ev.get("note"),
                }
                for ev in evidence
            ],
        }
        if isinstance(section.get("coverage"), dict):
            normalized_section["coverage"] = section.get("coverage")
        normalized_sections.append(normalized_section)

    report_json = {
        "report_id": report_id,
        "job_id": job_id,
        "report_type": report_type,
        "title": title,
        "generated_at": generated_at,
        "metadata": metadata or {},
        "sections": normalized_sections,
        "appendix_sources": (metadata or {}).get("appendix_sources", []),
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
    retrieval_summary = (metadata or {}).get("retrieval_summary") if isinstance(metadata, dict) else None
    if isinstance(retrieval_summary, dict) and retrieval_summary:
        html_body.append("<h2>調査範囲</h2>")
        html_body.append("<ul>")
        for key in ("candidate_count", "valid_source_count", "evidence_count", "official_source_count", "pdf_source_count", "high_quality_source_count"):
            html_body.append(f"<li>{html.escape(key)}: {html.escape(str(retrieval_summary.get(key, 0)))}</li>")
        html_body.append("</ul>")
    for section in normalized_sections:
        html_body.append(f"<h2>{html.escape(section['heading'])}</h2>")
        if section["summary"]:
            html_body.append(f"<p>{html.escape(section['summary'])}</p>")
        if section["evidence"]:
            html_body.append("<ul>")
            for ev in section["evidence"]:
                citation = html.escape(ev.get("citation_label") or "[citation missing]")
                url = html.escape(ev.get("source_url") or ev.get("url") or "")
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
        "markdown_path": str(report_md_path),
        "json_path": str(report_json_path),
        "html_path": str(report_html_path),
        "report_md_path": str(report_md_path),
        "report_json_path": str(report_json_path),
        "report_html_path": str(report_html_path),
        "generated_at": generated_at,
        "metadata": metadata or {},
    }


def save_report_record(report: dict) -> None:
    created_at = _now_iso()
    project = str(report.get("project") or "default")
    with transaction() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO nexus_reports(
                report_id, project, job_id, report_type, title, report_dir,
                markdown_path, json_path, html_path,
                report_md_path, report_json_path, report_html_path,
                summary, metadata, generated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["report_id"],
                project,
                report["job_id"],
                report["report_type"],
                report["title"],
                report["report_dir"],
                report["markdown_path"],
                report["json_path"],
                report["html_path"],
                report["report_md_path"],
                report["report_json_path"],
                report["report_html_path"],
                str(report.get("summary") or ""),
                json.dumps(report.get("metadata") or {}, ensure_ascii=False),
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
                markdown_path, json_path, html_path,
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
    evidence_count = len(evidence_items)
    evidence_summary = (
        f"Collected evidence count: {evidence_count}" if evidence_items else "No evidence was found for this job."
    )

    chapter_defaults: dict[str, str] = {
        "調査目的": "この章では、調査対象・背景・意思決定に必要な問いを定義します。",
        "条件": "この章では、調査範囲・期間・前提条件・制約を明示します。",
        "結論": "この章では、Evidence 章の根拠に基づく結論を記載します。",
        "比較": "この章では、候補間の比較軸と差分を整理します。",
        "不確実性": "この章では、データ欠損・バイアス・時点差による不確実性を明示します。",
        "Evidence": evidence_summary,
    }

    sections: list[dict] = []
    for heading in STANDARD_CHAPTERS:
        sections.append(
            {
                "heading": heading,
                "summary": chapter_defaults[heading],
                "evidence": evidence_items if heading == "Evidence" else [],
            }
        )
    return sections


def _load_latest_research_answer(job_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT answer_id, question, answer_markdown, evidence_json, answer_json, created_at
            FROM nexus_research_answers
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        return {}
    answer: dict = {}
    raw = str(row["answer_json"] or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = {}
        if isinstance(parsed, dict):
            answer.update(parsed)
    answer.setdefault("answer_id", row["answer_id"])
    answer.setdefault("question", row["question"])
    answer.setdefault("answer_markdown", row["answer_markdown"])
    answer.setdefault("created_at", row["created_at"])
    return answer




_MARKET_HEADING_DIMENSIONS: dict[str, list[str]] = {
    "executive summary": ["market_size", "key_players", "technology_trends", "regulation", "investment", "risks", "timeline"],
    "要約": ["market_size", "key_players", "technology_trends", "regulation", "investment", "risks", "timeline"],
    "市場概況": ["market_size"],
    "主要ドライバー": ["market_size", "technology_trends", "regulation", "investment"],
    "技術動向": ["technology_trends", "academic_evidence"],
    "主要プレイヤー": ["key_players"],
    "政策・規制": ["regulation", "official_policy"],
    "政策/規制": ["regulation", "official_policy"],
    "投資・提携": ["investment"],
    "リスク・制約": ["risks"],
    "今後12〜36か月の見通し": ["timeline", "market_size"],
    "根拠と不確実性": ["risks", "market_size", "key_players", "technology_trends", "regulation", "investment", "timeline"],
    "追加調査項目": ["risks", "timeline"],
}

_DIMENSION_LABELS: dict[str, str] = {
    "market_size": "市場規模・成長性",
    "key_players": "主要プレイヤー",
    "technology_trends": "技術動向",
    "regulation": "政策・規制",
    "supply_chain": "サプライチェーン",
    "risks": "リスク・制約",
    "timeline": "今後12〜36か月の見通し",
    "investment": "投資・提携",
    "official_policy": "公式政策",
    "academic_evidence": "学術・技術根拠",
}

_DIMENSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market_size": ("市場", "規模", "market", "size", "forecast", "予測", "cagr", "growth"),
    "key_players": ("企業", "players", "oem", "supplier", "メーカー", "competition", "share", "主要"),
    "technology_trends": ("技術", "battery", "propulsion", "semiconductor", "materials", "technology", "roadmap"),
    "regulation": ("規制", "認証", "policy", "regulation", "certification", "官公庁", "standard"),
    "supply_chain": ("供給", "supply", "chain", "manufacturing", "調達"),
    "risks": ("risk", "課題", "制約", "safety", "安全", "bottleneck", "uncertain", "リスク"),
    "timeline": ("timeline", "roadmap", "期限", "実用化", "launch", "12", "36", "見通し"),
    "investment": ("投資", "funding", "investment", "提携", "partnership", "subsidy", "資金"),
    "official_policy": ("official", "政策", "政府", "ministry", "agency", "官公庁"),
    "academic_evidence": ("論文", "study", "research", "journal", "academic", "研究"),
}


def _coerce_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _focused_plan_from_answer(answer: dict, retrieval_summary: dict) -> dict:
    plan = answer.get("focused_research_plan") if isinstance(answer.get("focused_research_plan"), dict) else {}
    if plan:
        return plan
    return retrieval_summary.get("focused_research_plan") if isinstance(retrieval_summary.get("focused_research_plan"), dict) else {}


def _normalize_evidence_pool(answer: dict, evidence_items: list[dict]) -> list[dict]:
    pool: list[dict] = []
    for source in (evidence_items, _coerce_list(answer.get("evidence_json")), _coerce_list(answer.get("evidence")), _coerce_list(answer.get("references"))):
        for raw in source:
            if isinstance(raw, dict):
                pool.append(raw)
    seen: set[str] = set()
    normalized: list[dict] = []
    for idx, ev in enumerate(pool, start=1):
        label = str(ev.get("citation_label") or ev.get("source_label") or ev.get("label") or "").strip()
        if not label:
            label = f"[S{idx}]"
        url = str(ev.get("url") or ev.get("source_url") or ev.get("final_url") or "").strip()
        title = str(ev.get("title") or ev.get("name") or ev.get("publisher") or "").strip()
        quote = str(ev.get("quote") or ev.get("text") or ev.get("snippet") or ev.get("summary") or "").strip()
        key = f"{label}|{url}|{title}|{quote[:60]}"
        if key in seen:
            continue
        seen.add(key)
        item = dict(ev)
        item["citation_label"] = label
        if url:
            item["url"] = url
            item.setdefault("source_url", url)
        if title:
            item["title"] = title
        if quote:
            item["quote"] = quote
        normalized.append(item)
    return normalized


def _coverage_by_dimension(coverage_matrix: list[dict]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for row in coverage_matrix:
        if not isinstance(row, dict):
            continue
        dim = str(row.get("dimension") or row.get("name") or "").strip()
        if dim:
            rows[dim] = row
    return rows


def _map_heading_to_dimensions(heading: str, focused_plan: dict, coverage_matrix: list[dict]) -> list[str]:
    heading_text = str(heading or "").strip()
    lowered = heading_text.lower()
    for key, dims in _MARKET_HEADING_DIMENSIONS.items():
        if lowered == key.lower() or heading_text == key:
            return [dim for dim in dims if dim]
    available = list(dict.fromkeys(list(focused_plan.get("must_cover_dimensions") or []) + [str(row.get("dimension")) for row in coverage_matrix if isinstance(row, dict) and row.get("dimension")]))
    matched: list[str] = []
    haystack = lowered + " " + heading_text
    for dim in available:
        label = _DIMENSION_LABELS.get(dim, dim.replace("_", " "))
        if dim.replace("_", " ").lower() in haystack or label.lower() in haystack or label in heading_text:
            matched.append(dim)
            continue
        if any(str(keyword).lower() in haystack for keyword in _DIMENSION_KEYWORDS.get(dim, (dim,))):
            matched.append(dim)
    if not matched and "不確実" in heading_text:
        matched = [dim for dim in available if str(_coverage_by_dimension(coverage_matrix).get(dim, {}).get("status") or "") in {"weak", "missing"}]
    return matched[:8]


def _evidence_matches_dimension(ev: dict, dim: str) -> bool:
    text = f"{ev.get('title','')} {ev.get('quote','')} {ev.get('text','')} {ev.get('snippet','')} {ev.get('note','')} {ev.get('url','')}".lower()
    return any(keyword.lower() in text for keyword in _DIMENSION_KEYWORDS.get(dim, (dim.replace("_", " "),)))


def _select_section_evidence(heading: str, dimensions: list[str], evidence_pool: list[dict], coverage_rows: dict[str, dict], *, limit: int = 7) -> list[dict]:
    if not evidence_pool:
        return []
    preferred_labels: list[str] = []
    for dim in dimensions:
        for label in coverage_rows.get(dim, {}).get("best_sources") or []:
            if str(label) not in preferred_labels:
                preferred_labels.append(str(label))
    scored: list[tuple[int, int, dict]] = []
    heading_lower = str(heading or "").lower()
    for idx, ev in enumerate(evidence_pool):
        label = str(ev.get("citation_label") or "")
        score = 0
        if label in preferred_labels:
            score += 50 - min(preferred_labels.index(label), 30)
        for dim in dimensions:
            if _evidence_matches_dimension(ev, dim):
                score += 15
        text = f"{ev.get('title','')} {ev.get('quote','')} {ev.get('snippet','')}".lower()
        for token in re.findall(r"[\w\u3040-\u30ff\u3400-\u9fff]+", heading_lower):
            if len(token) >= 2 and token in text:
                score += 2
        if score > 0 or not dimensions:
            scored.append((score, -idx, ev))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [ev for score, _idx, ev in scored if score > 0][:limit]
    if not selected and dimensions:
        selected = evidence_pool[: min(limit, len(evidence_pool))]
    if not dimensions and heading_lower in {"executive summary", "要約"}:
        selected = evidence_pool[: min(limit, len(evidence_pool))]
    return selected


def _compact_evidence_sentence(ev: dict) -> str:
    label = str(ev.get("citation_label") or "[citation missing]").strip()
    title = _safe_quote(str(ev.get("title") or ev.get("publisher") or "根拠資料"), 90)
    quote = _safe_quote(str(ev.get("quote") or ev.get("snippet") or ev.get("text") or ""), 180)
    if quote:
        return f"{title} は「{quote}」という範囲の情報を示している {label}。"
    return f"{title} を根拠として確認できる {label}。"


def _deterministic_section_summary(*, heading: str, question: str, dimensions: list[str], section_evidence: list[dict], coverage_rows: dict[str, dict], conclusion: str) -> str:
    labels = [_DIMENSION_LABELS.get(dim, dim.replace("_", " ")) for dim in dimensions]
    status_bits = []
    for dim in dimensions:
        row = coverage_rows.get(dim, {})
        if row:
            status_bits.append(f"{_DIMENSION_LABELS.get(dim, dim)}={row.get('status', 'unknown')}({row.get('evidence_count', 0)}件)")
    if str(heading).lower() in {"executive summary", "要約"} and conclusion:
        intro = f"本章では、{question}について、後続章の根拠を横断して要点をまとめる。{_safe_quote(conclusion, 260)}"
    else:
        intro = f"本章（{heading}）では、{question}のうち{ '、'.join(labels) if labels else '関連論点' }を中心に、収集済みEvidenceから確認できる事実と解釈を分けて整理する。"
    evidence_sentences = [_compact_evidence_sentence(ev) for ev in section_evidence[:5]]
    if evidence_sentences:
        body = " ".join(evidence_sentences)
    else:
        body = "この章に直接対応するEvidenceは十分ではないため、既存の回答本文とCoverage Matrixに基づく限定的な整理に留める。"
    uncertainty_rows = [coverage_rows.get(dim, {}) for dim in dimensions if str(coverage_rows.get(dim, {}).get("status") or "") in {"weak", "missing"}]
    uncertainty = ""
    if uncertainty_rows:
        bits = []
        for row in uncertainty_rows:
            dim = str(row.get("dimension") or "")
            bits.append(f"{_DIMENSION_LABELS.get(dim, dim)}は{row.get('status')}（{row.get('notes') or '根拠が限定的'}）")
        uncertainty = " 不確実性: " + "、".join(bits) + "。"
    elif status_bits:
        uncertainty = " Coverage Matrix上の確認状況は " + " / ".join(status_bits) + "。"
    synthesis = " ".join(part for part in (intro, body, uncertainty) if part).strip()
    if len(synthesis) < 300 and section_evidence:
        synthesis += " したがって、本章の結論は単一資料の断片ではなく、複数の出典に共通する方向性を優先して読む必要がある。ただし、数値・時点・地域範囲が資料ごとに異なる場合は、本文中のcitationを起点に原典で前提を確認することが望ましい。"
    return synthesis[:1200]


def _report_section_llm_settings() -> dict:
    enabled = str(os.environ.get("NEXUS_REPORT_SECTION_LLM_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
    endpoint = str(os.environ.get("NEXUS_REPORT_SECTION_LLM_ENDPOINT") or os.environ.get("ANSWER_LLM_ENDPOINT") or os.environ.get("DEEP_RESEARCH_LLM_ENDPOINT") or "").strip()
    model = str(os.environ.get("NEXUS_REPORT_SECTION_LLM_MODEL") or os.environ.get("ANSWER_LLM_MODEL") or "local-llm").strip() or "local-llm"
    return {"enabled": enabled, "endpoint": endpoint, "model": model}


def _synthesize_section_with_llm(*, heading: str, question: str, dimensions: list[str], section_evidence: list[dict], coverage_rows: dict[str, dict], fallback: str) -> tuple[str, dict]:
    settings = _report_section_llm_settings()
    if not settings["enabled"] or not settings["endpoint"] or not section_evidence:
        return fallback, {"mode": "deterministic", "reason": "section_llm_disabled_or_no_evidence"}
    evidence_text = "\n".join(_compact_evidence_sentence(ev) for ev in section_evidence[:8])
    coverage_text = json.dumps([coverage_rows.get(dim, {"dimension": dim}) for dim in dimensions], ensure_ascii=False)
    prompt = (
        "日本語で300〜800字程度のレポート章本文を作成してください。"
        "Evidence以外の断定は避け、重要な文に[S1]形式のcitationを付け、missing/weak coverageは不確実性として明示してください。\n"
        f"質問: {question}\n章: {heading}\n対応dimension: {', '.join(dimensions)}\nCoverage: {coverage_text}\nEvidence:\n{evidence_text}"
    )
    payload = {"model": settings["model"], "messages": [{"role": "system", "content": "You write grounded Japanese research report sections."}, {"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 900, "stream": False}
    req = request.Request(settings["endpoint"], data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=float(os.environ.get("NEXUS_REPORT_SECTION_LLM_TIMEOUT_SEC", "8"))) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        choices = parsed.get("choices") if isinstance(parsed, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        content = str(message.get("content") or "").strip() if isinstance(message, dict) else ""
        if len(content) >= 120:
            return content, {"mode": "llm", "model": settings["model"], "endpoint": settings["endpoint"]}
    except (TimeoutError, error.HTTPError, error.URLError, ValueError, TypeError, OSError) as exc:
        return fallback, {"mode": "deterministic", "reason": f"section_llm_failed:{exc}"}
    return fallback, {"mode": "deterministic", "reason": "section_llm_empty_or_short"}


def _build_section_wise_outline_sections(job_id: str, answer: dict, evidence_items: list[dict], question: str, conclusion: str, scope_summary: str) -> tuple[list[dict], list[dict]]:
    retrieval_summary = answer.get("retrieval_summary") if isinstance(answer.get("retrieval_summary"), dict) else {}
    focused_plan = _focused_plan_from_answer(answer, retrieval_summary)
    coverage_matrix = answer.get("coverage_matrix") if isinstance(answer.get("coverage_matrix"), list) else retrieval_summary.get("coverage_matrix") if isinstance(retrieval_summary.get("coverage_matrix"), list) else []
    outline = [str(item).strip() for item in list(answer.get("report_outline") or retrieval_summary.get("report_outline") or []) if str(item).strip()]
    evidence_pool = _normalize_evidence_pool(answer, evidence_items)
    coverage_rows = _coverage_by_dimension(coverage_matrix)
    sections: list[dict] = [
        {"heading": "調査目的", "summary": question, "evidence": []},
        {"heading": "調査範囲", "summary": scope_summary, "evidence": []},
    ]
    section_coverage: list[dict] = []
    for heading in outline:
        dims = _map_heading_to_dimensions(heading, focused_plan, coverage_matrix)
        section_evidence = _select_section_evidence(heading, dims, evidence_pool, coverage_rows)
        fallback = _deterministic_section_summary(heading=heading, question=question or job_id, dimensions=dims, section_evidence=section_evidence, coverage_rows=coverage_rows, conclusion=conclusion)
        summary, generation = _synthesize_section_with_llm(heading=heading, question=question or job_id, dimensions=dims, section_evidence=section_evidence, coverage_rows=coverage_rows, fallback=fallback)
        statuses = [str(coverage_rows.get(dim, {}).get("status") or "unknown") for dim in dims]
        weak_or_missing = [dim for dim in dims if str(coverage_rows.get(dim, {}).get("status") or "") in {"weak", "missing"}]
        coverage_entry = {
            "heading": heading,
            "dimensions": dims,
            "status": "missing" if "missing" in statuses else "weak" if "weak" in statuses else "covered" if dims else "unmapped",
            "evidence_count": len(section_evidence),
            "citations": [ev.get("citation_label") for ev in section_evidence if ev.get("citation_label")],
            "weak_or_missing_dimensions": weak_or_missing,
            "generation": generation,
        }
        section_coverage.append(coverage_entry)
        sections.append({"heading": heading, "summary": summary, "evidence": section_evidence, "coverage": coverage_entry})
    source_mix = answer.get("source_mix_summary") if isinstance(answer.get("source_mix_summary"), dict) else retrieval_summary.get("source_mix", {})
    sections.extend([
        {"heading": "Coverage Matrix", "summary": json.dumps(coverage_matrix, ensure_ascii=False, indent=2), "evidence": []},
        {"heading": "Source Mix", "summary": json.dumps(source_mix, ensure_ascii=False, indent=2), "evidence": []},
    ])
    return sections, section_coverage

def _section_between_headings(markdown: str, heading_pattern: str, stop_pattern: str | None = None) -> str:
    lines = str(markdown or "").splitlines()
    start: int | None = None
    heading_re = re.compile(heading_pattern, re.IGNORECASE)
    stop_re = re.compile(stop_pattern, re.IGNORECASE) if stop_pattern else None
    for idx, line in enumerate(lines):
        if heading_re.match(line.strip()):
            start = idx + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start, len(lines)):
        stripped = lines[idx].strip()
        if stop_re and stop_re.match(stripped):
            end = idx
            break
        if not stop_re and re.match(r"^#{1,6}\s+", stripped):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def _extract_structured_answer_section(markdown: str) -> str:
    raw = str(markdown or "")
    answer_section = _section_between_headings(
        raw,
        r"^##\s+Answer\s*$",
        r"^##\s+(References|Sources|参考|出典)\s*$",
    )
    if answer_section:
        return answer_section
    return _section_between_headings(raw, r"^##\s+結論\s*$")


def _extract_answer_section(markdown: str) -> str:
    """Extract the substantive conclusion from an answer markdown document."""
    raw = str(markdown or "")
    structured = _extract_structured_answer_section(raw)
    if structured:
        return structured

    paragraph_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph_lines:
                break
            continue
        if re.match(r"^#{1,6}\s+", stripped):
            if paragraph_lines:
                break
            continue
        paragraph_lines.append(stripped)
    return "\n".join(paragraph_lines).strip()

def _build_sections_from_research_answer(job_id: str, answer: dict, evidence_items: list[dict]) -> list[dict]:
    question = str(answer.get("question") or answer.get("query") or job_id)
    answer_markdown = str(answer.get("answer_markdown") or answer.get("answer") or "")
    conclusion = (
        _extract_structured_answer_section(answer_markdown)
        or str(answer.get("summary") or "")
        or _extract_answer_section(answer_markdown)
    )
    retrieval_summary = answer.get("retrieval_summary") if isinstance(answer.get("retrieval_summary"), dict) else {}
    claim_analysis = answer.get("claim_analysis") if isinstance(answer.get("claim_analysis"), dict) else {}
    claims = list(claim_analysis.get("claims") or [])
    if claims:
        claim_lines = []
        for claim in claims[:20]:
            status = claim.get("status") or "candidate"
            text = claim.get("claim") or claim.get("text") or ""
            citations = " ".join(claim.get("citations") or [])
            claim_lines.append(f"- {status}: {text} {citations}".strip())
        claims_summary = "\n".join(claim_lines)
    else:
        claims_summary = "Claim-level analysis is not available for this answer."
    unresolved = list(claim_analysis.get("unresolved_items") or answer.get("unresolved_items") or [])
    refs = list(answer.get("references") or [])
    uncertainty_bits = []
    if answer.get("stub_sources_filtered"):
        uncertainty_bits.append("stub search results were filtered")
    if int(claim_analysis.get("unsupported_claim_count") or 0):
        uncertainty_bits.append(f"unsupported_claims={claim_analysis.get('unsupported_claim_count')}")
    if int(claim_analysis.get("unresolved_claim_count") or 0):
        uncertainty_bits.append(f"unresolved_claims={claim_analysis.get('unresolved_claim_count')}")
    if int(claim_analysis.get("weakly_supported_claim_count") or 0):
        uncertainty_bits.append(f"weakly_supported_claims={claim_analysis.get('weakly_supported_claim_count')}")
    if int(claim_analysis.get("low_quality_supported_claim_count") or 0):
        uncertainty_bits.append(f"low_quality_supported_claims={claim_analysis.get('low_quality_supported_claim_count')}")
    if int(claim_analysis.get("contradiction_count") or 0):
        uncertainty_bits.append(f"possible_contradictions={claim_analysis.get('contradiction_count')}")
    for warning in list(claim_analysis.get("source_quality_warnings") or [])[:3]:
        uncertainty_bits.append(str(warning))
    scope_summary = "Retrieval summary is not available."
    if retrieval_summary:
        unsatisfied = ", ".join(retrieval_summary.get("unsatisfied_targets") or [])
        scope_summary = (
            f"候補件数={retrieval_summary.get('candidate_count', 0)} / "
            f"有効ソース件数={retrieval_summary.get('valid_source_count', 0)} / "
            f"Evidence件数={retrieval_summary.get('evidence_count', 0)} / "
            f"公式={retrieval_summary.get('official_source_count', 0)} / "
            f"PDF={retrieval_summary.get('pdf_source_count', 0)} / "
            f"高品質={retrieval_summary.get('high_quality_source_count', 0)}"
        )
        if unsatisfied:
            scope_summary += f"\n未達成target: {unsatisfied}"
    outline = list(answer.get("report_outline") or retrieval_summary.get("report_outline") or [])
    if outline:
        sections, section_coverage = _build_section_wise_outline_sections(job_id, answer, evidence_items, question, conclusion, scope_summary)
        answer["section_coverage"] = section_coverage
        sections.append({"heading": "Sources / Evidence", "summary": f"references={len(refs)}, evidence_count={len(evidence_items)}", "evidence": _normalize_evidence_pool(answer, evidence_items)[:80]})
        return sections
    return [
        {"heading": "調査目的", "summary": question, "evidence": []},
        {"heading": "調査範囲", "summary": scope_summary, "evidence": []},
        {"heading": "結論", "summary": conclusion, "evidence": []},
        {"heading": "主要主張と根拠", "summary": claims_summary, "evidence": []},
        {"heading": "追加確認が必要な点", "summary": "\n".join(f"- {item}" for item in unresolved) if unresolved else "追加確認項目は検出されていません。", "evidence": []},
        {"heading": "Sources / Evidence", "summary": f"references={len(refs)}, evidence_count={len(evidence_items)}", "evidence": evidence_items or refs},
        {"heading": "不確実性", "summary": "; ".join(uncertainty_bits) if uncertainty_bits else "重大な不確実性は検出されていません。", "evidence": []},
    ]


class BuildReportRequest(BaseModel):
    job_id: str = Field(min_length=1)
    report_type: str = Field(default="general", min_length=1)
    title: str | None = None


def _path_status(path_value: str | None) -> dict[str, object]:
    raw = str(path_value or "").strip()
    exists = False
    if raw:
        try:
            exists = Path(raw).exists()
        except OSError:
            exists = False
    return {"path": raw, "exists": exists}


@nexus_report_router.get("/reports")
@nexus_report_router.get("/report/list")
def list_reports(
    project: str = Query("default"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT report_id, title, report_type, generated_at, job_id
            FROM nexus_reports
            WHERE project = ?
            ORDER BY generated_at DESC, created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ).fetchall()
    return {"reports": [dict(row) for row in rows]}


@nexus_report_router.get("/reports/{report_id}")
def get_report_detail(report_id: str, project: str = Query("default")) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                report_id, title, report_type, generated_at, job_id,
                markdown_path, json_path, html_path,
                report_md_path, report_json_path, report_html_path
            FROM nexus_reports
            WHERE report_id = ? AND project = ?
            """,
            (report_id, project),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="report not found")

    return {
        "report": {
            "report_id": row["report_id"],
            "title": row["title"],
            "report_type": row["report_type"],
            "generated_at": row["generated_at"],
            "job_id": row["job_id"],
            "markdown_path": str(row["markdown_path"] or row["report_md_path"] or ""),
            "json_path": str(row["json_path"] or row["report_json_path"] or ""),
            "html_path": str(row["html_path"] or row["report_html_path"] or ""),
            "report_md_path": str(row["report_md_path"] or row["markdown_path"] or ""),
            "report_json_path": str(row["report_json_path"] or row["json_path"] or ""),
            "report_html_path": str(row["report_html_path"] or row["html_path"] or ""),
            "report_md": _path_status(row["markdown_path"] or row["report_md_path"]),
            "report_json": _path_status(row["json_path"] or row["report_json_path"]),
            "report_html": _path_status(row["html_path"] or row["report_html_path"]),
        }
    }


def build_job_report(payload: BuildReportRequest) -> dict:
    job = get_job(payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    evidence_items = list_evidence_items(payload.job_id)
    answer = _load_latest_research_answer(payload.job_id)
    if answer:
        sections = _build_sections_from_research_answer(payload.job_id, answer, evidence_items)
        metadata_source = "research_answer"
    else:
        sections = _build_sections_from_evidence(evidence_items)
        metadata_source = "evidence_only"
    title = payload.title or f"Nexus Report ({payload.job_id})"
    retrieval_summary = answer.get("retrieval_summary") if isinstance(answer.get("retrieval_summary"), dict) else {}
    claim_analysis = answer.get("claim_analysis") if isinstance(answer.get("claim_analysis"), dict) else {}
    report_metadata = {
        "source": metadata_source,
        "answer_id": answer.get("answer_id"),
        "retrieval_summary": answer.get("retrieval_summary") if isinstance(answer.get("retrieval_summary"), dict) else {},
        "appendix_sources": list(answer.get("evidence_json") or answer.get("evidence") or [])[:500],
        "section_coverage": list(answer.get("section_coverage") or []),
        "focused_research_plan": (retrieval_summary.get("focused_research_plan") if isinstance(retrieval_summary, dict) else {}) or {},
        "coverage_matrix": answer.get("coverage_matrix") if isinstance(answer.get("coverage_matrix"), list) else (retrieval_summary.get("coverage_matrix") if isinstance(retrieval_summary, dict) else []),
        "claim_analysis": {
            "claim_count": claim_analysis.get("claim_count", 0),
            "supported_claim_count": claim_analysis.get("supported_claim_count", 0),
            "weakly_supported_claim_count": claim_analysis.get("weakly_supported_claim_count", 0),
            "unsupported_claim_count": claim_analysis.get("unsupported_claim_count", 0),
            "unresolved_claim_count": claim_analysis.get("unresolved_claim_count", 0),
            "average_source_quality_score": claim_analysis.get("average_source_quality_score", 0.0),
            "high_quality_supported_claim_count": claim_analysis.get("high_quality_supported_claim_count", 0),
            "low_quality_supported_claim_count": claim_analysis.get("low_quality_supported_claim_count", 0),
            "contradiction_count": claim_analysis.get("contradiction_count", 0),
            "source_quality_warnings": claim_analysis.get("source_quality_warnings", []),
            "contradictions": list(claim_analysis.get("contradictions") or [])[:5],
            "gaps": claim_analysis.get("gaps", []),
        },
        "evidence_count": len(evidence_items),
        "generated_at": _now_iso(),
    }

    report = build_report(
        job_id=payload.job_id,
        report_type=payload.report_type,
        title=title,
        sections=sections,
        metadata=report_metadata,
    )
    report["project"] = "default"
    save_report_record(report)
    return report
