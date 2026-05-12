from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

_DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "market_size": ["市場", "規模", "market", "size", "forecast", "予測", "cagr"],
    "key_players": ["企業", "players", "oem", "supplier", "メーカー", "competition"],
    "technology_trends": ["技術", "battery", "propulsion", "semiconductor", "materials", "technology"],
    "regulation": ["規制", "認証", "policy", "regulation", "certification", "官公庁"],
    "supply_chain": ["供給", "supply", "chain", "manufacturing", "調達"],
    "risks": ["risk", "課題", "制約", "safety", "安全", "bottleneck"],
    "timeline": ["timeline", "roadmap", "期限", "実用化", "launch"],
    "investment": ["投資", "funding", "investment", "提携", "partnership", "subsidy"],
    "official_policy": ["official", "政策", "政府", "ministry", "agency"],
    "academic_evidence": ["論文", "study", "research", "journal", "academic"],
}

_OFFICIAL_SUFFIXES = (".gov", ".go.jp", ".europa.eu", ".int", ".edu", ".ac.jp", ".mil")
_ACADEMIC_DOMAINS = ("arxiv.org", "doi.org", "sciencedirect.com", "springer.com", "ieee.org", "nature.com", "researchgate.net", "semanticscholar.org")
_NEWS_HINTS = ("news", "reuters", "bloomberg", "nikkei", "nhk", "cnn", "bbc", "press")
_COMPANY_HINTS = ("ir.", "investor", "annual", "company", "corp", "inc", "airbus", "boeing", "infineon", "rohm", "toshiba")
_REPORT_HINTS = ("report", "whitepaper", "white paper", "pdf", "調査", "報告書", "白書", "forecast")

_PROFILE_QUERY_TERMS: dict[str, dict[str, str]] = {
    "news": {"ja": "最新 今日 速報 news latest press release", "en": "latest today breaking news press release"},
    "market": {"ja": "市場規模 CAGR 予測 主要企業 投資 partnership market outlook", "en": "market size CAGR forecast key companies investment partnership market outlook"},
    "official": {"ja": "公式 官公庁 白書 報告書 site:go.jp site:.gov PDF", "en": "official government white paper report site:.gov site:go.jp PDF"},
    "source": {"ja": "PDF report white paper annual report investor relations", "en": "PDF report white paper annual report investor relations"},
    "academic": {"ja": "paper arxiv study review IEEE 論文", "en": "paper arxiv study review IEEE"},
}


def _profile_query_terms(profile: str, lang: str) -> str:
    terms = _PROFILE_QUERY_TERMS.get(str(profile or "").lower()) or {}
    return terms.get("ja" if lang == "ja" else "en", "")



def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[\w\u3040-\u30ff\u3400-\u9fff]+", str(text or "")) if len(m.group(0)) >= 2}


def _is_ja(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text or ""))


def _domain(url: str) -> str:
    return urlparse(str(url or "")).netloc.lower()


def classify_source_type(item: dict[str, Any]) -> str:
    url = str(item.get("url") or item.get("final_url") or "")
    title = str(item.get("title") or "")
    snippet = str(item.get("snippet") or "")
    domain = _domain(url)
    haystack = f"{url} {title} {snippet}".lower()
    if url.lower().endswith(".pdf") or "pdf" in str(item.get("content_type") or "").lower():
        return "pdf"
    if domain.endswith(_OFFICIAL_SUFFIXES) or any(token in domain for token in ("nasa.gov", "faa.gov", "meti.go.jp", "nedo.go.jp")):
        return "official"
    if any(token in haystack for token in _ACADEMIC_DOMAINS) or any(token in haystack for token in ("journal", "paper", "論文", "academic")):
        return "academic"
    if any(token in haystack for token in _REPORT_HINTS):
        return "report"
    if any(token in haystack for token in _COMPANY_HINTS):
        return "company_ir"
    if any(token in haystack for token in _NEWS_HINTS) or str(item.get("source_type") or "").lower() == "news":
        return "news"
    if ".org" in domain:
        return "industry_association"
    return str(item.get("source_type") or "web") or "web"


def get_screening_settings(depth: str | None) -> dict[str, int | bool]:
    key = str(depth or "standard").lower()
    if key == "deep":
        return {"enabled": True, "target_screening_candidates": 200, "max_screening_queries": 16, "max_results_per_query": 15}
    if key == "exhaustive":
        return {"enabled": True, "target_screening_candidates": 350, "max_screening_queries": 24, "max_results_per_query": 20}
    return {"enabled": False, "target_screening_candidates": 60, "max_screening_queries": 6, "max_results_per_query": 10}


def infer_research_intent(query: str, source_profile: str | None, depth: str) -> dict[str, Any]:
    q = str(query or "").strip()
    q_lower = q.lower()
    profile = str(source_profile or "").strip().lower() or "general"
    expected = "report"
    if any(token in q_lower for token in ("比較", "compare", "comparison", "vs")):
        expected = "comparison"
    if any(token in q_lower for token in ("市場", "動向", "予測", "market", "forecast", "trend")):
        expected = "market_analysis"
        profile = "market"
    if any(token in q_lower for token in ("ニュース", "最新", "速報", "news", "latest")):
        expected = "news_update"
        profile = "news" if profile in {"general", "web"} else profile
    if any(token in q_lower for token in ("論文", "研究", "academic", "paper", "technical", "技術調査")):
        expected = "technical_survey"
        profile = "academic" if "論文" in q_lower or "paper" in q_lower else "technical"
    if any(token in q_lower for token in ("公式", "一次資料", "官公庁", "official", "government")):
        expected = "official_source_review"
        profile = "official"
    language = "ja" if _is_ja(q) else "en"
    if any(token in q_lower for token in ("最新", "latest", "today", "速報")):
        horizon = "latest"
    elif "2026" in q_lower or "今年" in q_lower or "current year" in q_lower:
        horizon = "current_year"
    elif any(token in q_lower for token in ("12か月", "12ヶ月", "last 12", "past year")):
        horizon = "last_12_months"
    elif any(token in q_lower for token in ("歴史", "historical", "推移")):
        horizon = "historical"
    else:
        horizon = "unspecified"
    if any(token in q_lower for token in ("日本", "japan", "国内")):
        geography = "japan"
    elif any(token in q_lower for token in ("米国", "us", "u.s.", "america")):
        geography = "us"
    elif any(token in q_lower for token in ("eu", "欧州", "europe")):
        geography = "eu"
    elif any(token in q_lower for token in ("世界", "global", "グローバル")):
        geography = "global"
    else:
        geography = "unspecified"
    dimensions = ["timeline", "risks"]
    if expected == "market_analysis":
        dimensions = ["market_size", "key_players", "technology_trends", "regulation", "investment", "risks", "timeline"]
    elif expected == "technical_survey":
        dimensions = ["technology_trends", "academic_evidence", "key_players", "risks", "timeline"]
    elif expected == "official_source_review":
        dimensions = ["official_policy", "regulation", "timeline", "risks"]
    elif expected == "news_update":
        dimensions = ["timeline", "key_players", "risks"]
    preferred = ["official", "report", "news"]
    if expected == "market_analysis":
        preferred = ["official", "pdf", "report", "press_release", "news", "company_ir", "industry_association"]
    elif expected == "technical_survey":
        preferred = ["academic", "pdf", "official", "report"]
    elif expected == "official_source_review":
        preferred = ["official", "press_release", "pdf", "report"]
    return {
        "original_query": q,
        "normalized_topic": re.sub(r"(を調査して|について|調査|してください)$", "", q).strip() or q,
        "language": language,
        "expected_output_type": expected,
        "source_profile": profile if profile != "web" else "general",
        "time_horizon": horizon,
        "geography": geography,
        "required_dimensions": dimensions,
        "preferred_source_types": preferred,
        "depth": str(depth or "standard").lower(),
        "planner": "deterministic",
    }


def summarize_screening_candidates(candidates: list[dict[str, Any]], intent: dict[str, Any]) -> dict[str, Any]:
    domain_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    freshness_counts: Counter[str] = Counter()
    dimension_hits: dict[str, int] = defaultdict(int)
    buckets: dict[str, list[dict[str, Any]]] = {"official": [], "report": [], "academic": [], "news": [], "company_ir": []}
    current_year = datetime.now(timezone.utc).year
    topic_terms = _tokens(str(intent.get("normalized_topic") or intent.get("original_query") or ""))
    off_topic: Counter[str] = Counter()
    for item in candidates:
        url = str(item.get("url") or "")
        domain = str(item.get("domain") or _domain(url))
        if domain:
            domain_counts[domain] += 1
        stype = classify_source_type(item)
        source_counts[stype] += 1
        date = str(item.get("publishedDate") or item.get("published_at") or item.get("published_date") or item.get("date") or "")
        if str(current_year) in date:
            freshness_counts["current_year"] += 1
        elif any(str(y) in date for y in range(current_year - 1, current_year)):
            freshness_counts["last_12_months"] += 1
        elif date:
            freshness_counts["older"] += 1
        else:
            freshness_counts["unknown"] += 1
        haystack = f"{item.get('title','')} {item.get('snippet','')} {url}".lower()
        for dim, kws in _DIMENSION_KEYWORDS.items():
            if any(kw.lower() in haystack for kw in kws):
                dimension_hits[dim] += 1
        for key in buckets:
            if stype == key or (key == "report" and stype in {"report", "pdf"}):
                buckets[key].append(item)
        if topic_terms and not (topic_terms & _tokens(haystack)):
            for token in list(_tokens(str(item.get("title") or "")))[:3]:
                off_topic[token] += 1
    clusters = [{"name": dim, "candidate_count": count} for dim, count in sorted(dimension_hits.items(), key=lambda kv: kv[1], reverse=True) if count]
    required = list(intent.get("required_dimensions") or [])
    gaps = [dim for dim in required if dimension_hits.get(dim, 0) == 0]
    focus = required + [c["name"] for c in clusters[:4] if c["name"] not in required]
    return {
        "top_domains": [{"domain": d, "count": c} for d, c in domain_counts.most_common(12)],
        "source_type_counts": dict(source_counts),
        "freshness_counts": dict(freshness_counts),
        "topic_clusters": clusters,
        "likely_official_sources": buckets["official"][:10],
        "likely_reports": buckets["report"][:10],
        "likely_academic_sources": buckets["academic"][:10],
        "likely_news_sources": buckets["news"][:10],
        "likely_company_sources": buckets["company_ir"][:10],
        "gaps": gaps,
        "off_topic_patterns": [token for token, _ in off_topic.most_common(8)],
        "recommended_focus_areas": focus[:10],
        "candidate_count": len(candidates),
        "domain_count": len(domain_counts),
    }


def build_focused_research_plan(intent: dict[str, Any], screening_summary: dict[str, Any], *, depth: str) -> dict[str, Any]:
    topic = str(intent.get("normalized_topic") or intent.get("original_query") or "").strip()
    if not topic:
        topic = str(intent.get("original_query") or "research topic").strip()
    lang = str(intent.get("language") or "en")
    dims = list(dict.fromkeys(list(intent.get("required_dimensions") or []) + list(screening_summary.get("gaps") or [])))
    if not dims:
        dims = ["timeline", "risks"]
    purpose_terms_ja = {
        "market_size": "市場規模 予測 CAGR", "key_players": "主要企業 プレイヤー シェア", "technology_trends": "技術動向 課題 ロードマップ",
        "regulation": "規制 認証 政策 官公庁", "supply_chain": "サプライチェーン 供給 製造", "risks": "リスク 制約 課題",
        "timeline": "ロードマップ 実用化 時期", "investment": "投資 提携 資金調達", "official_policy": "公式 政策 発表", "academic_evidence": "論文 研究 技術"}
    purpose_terms_en = {
        "market_size": "market size forecast CAGR", "key_players": "key players companies share", "technology_trends": "technology trends roadmap challenges",
        "regulation": "regulation certification policy government", "supply_chain": "supply chain manufacturing", "risks": "risks constraints bottlenecks",
        "timeline": "roadmap commercialization timeline", "investment": "investment funding partnerships", "official_policy": "official policy announcement", "academic_evidence": "research papers technical evidence"}
    source_by_dim = {
        "market_size": ("market", ["report", "industry_association", "company_ir"]), "key_players": ("market", ["company_ir", "news", "report"]),
        "technology_trends": ("technical", ["academic", "report", "official"]), "regulation": ("official", ["official", "press_release", "report"]),
        "supply_chain": ("market", ["report", "company_ir", "industry_association"]), "risks": ("general", ["report", "news", "official"]),
        "timeline": ("news", ["news", "press_release", "company_ir"]), "investment": ("market", ["news", "company_ir", "press_release"]),
        "official_policy": ("official", ["official", "press_release", "pdf"]), "academic_evidence": ("academic", ["academic", "pdf", "report"]),
    }
    focused = []
    terms = purpose_terms_ja if lang == "ja" else purpose_terms_en
    for idx, dim in enumerate(dims):
        suffix = terms.get(dim, dim.replace("_", " "))
        profile, preferred = source_by_dim.get(dim, (str(intent.get("source_profile") or "general"), list(intent.get("preferred_source_types") or [])))
        profile_suffix = _profile_query_terms(profile, lang)
        focused.append({"query": " ".join(f"{topic} {suffix} {profile_suffix}".split()), "purpose": dim, "source_profile": profile, "preferred_source_types": preferred, "freshness": "recent" if intent.get("time_horizon") in {"latest", "current_year", "last_12_months"} or profile in {"news", "market"} else "balanced", "priority": round(max(0.45, 0.95 - idx * 0.04), 2)})
    if str(intent.get("expected_output_type")) == "market_analysis":
        extras = ["official statistics report", "industry association report", "company investor relations annual report", "market size CAGR forecast partnership market outlook"] if lang != "ja" else ["公式 統計 報告書", "業界団体 レポート", "企業 IR 統合報告書", "市場規模 CAGR 予測 主要企業 投資"]
        for extra in extras:
            focused.append({"query": " ".join(f"{topic} {extra}".split()), "purpose": "source_mix", "source_profile": "market", "preferred_source_types": ["official", "report", "company_ir"], "freshness": "balanced", "priority": 0.7})
    focused = [fq for fq in focused if len(_tokens(fq["query"])) > 1 and fq["query"].lower() not in {"web analysis", "analysis web"}]
    cap = 18 if str(depth).lower() == "exhaustive" else 12 if str(depth).lower() == "deep" else 8
    targets = {"official": 4, "report_pdf": 4, "news_recent": 4, "academic": 3, "company_ir": 3, "industry_association": 2}
    if str(intent.get("expected_output_type")) == "market_analysis":
        targets.update({"official": 8, "report_pdf": 8, "news_recent": 8, "academic": 4, "company_ir": 6, "industry_association": 4})
    if str(depth).lower() == "exhaustive":
        targets = {k: int(v * 1.5) for k, v in targets.items()}
    return {"research_questions": [f"{topic}: {dim}" for dim in dims], "focused_queries": focused[:cap], "must_cover_dimensions": dims, "source_mix_targets": targets, "exclusion_terms": list(screening_summary.get("off_topic_patterns") or [])[:10]}



def build_replenishment_queries(
    original_query: str,
    intent: dict,
    focused_plan: dict,
    retrieval_deficit: dict,
    failed_sources: list[dict],
    suspended_engines: list[str],
) -> list[dict]:
    """Build anchored replacement queries to refill failed/degraded/off-topic retrieval slots."""
    anchor = " ".join(str(original_query or "").split()).strip()
    if not anchor:
        return []
    profile = str((intent or {}).get("source_profile") or (focused_plan or {}).get("source_profile") or "market").lower()
    suspended = [str(engine).lower() for engine in suspended_engines or [] if str(engine).strip()]
    failure_types = [str(item.get("failure_class") or item.get("failure_type") or item.get("status") or "").lower() for item in failed_sources or []]
    off_topic_heavy = sum(1 for value in failure_types if "off" in value) >= 2
    exclude_domains = sorted({_domain(str(item.get("url") or item.get("final_url") or "")) for item in failed_sources or [] if _domain(str(item.get("url") or item.get("final_url") or ""))})[:12]
    exclusion_terms = list((focused_plan or {}).get("exclusion_terms") or [])[:8]
    if off_topic_heavy:
        exclusion_terms.extend(["semantic web", "web security", "unrelated", "definition only"])

    def engines() -> list[str]:
        primary = ["google", "brave", "duckduckgo"]
        return [engine for engine in primary if engine not in suspended] or (["wikipedia", "wikidata", "github"] + (["arxiv", "crossref", "openalex"] if profile in {"source", "academic", "technical"} else []))

    specs: list[tuple[str, str, list[str], float]] = []
    if int(retrieval_deficit.get("official_deficit") or 0) > 0:
        specs.append(("official government report PDF", "official_deficit", ["official", "report", "pdf"], 0.95))
    if int(retrieval_deficit.get("pdf_deficit") or 0) > 0:
        specs.append(("PDF report white paper", "pdf_deficit", ["pdf", "report"], 0.9))
    if int(retrieval_deficit.get("fresh_news_deficit") or 0) > 0:
        specs.append(("latest news press release 2026", "fresh_news_deficit", ["news", "press_release"], 0.86))
    if int(retrieval_deficit.get("company_ir_deficit") or 0) > 0:
        specs.append(("investor relations annual report company announcement", "company_ir_deficit", ["company_ir", "report"], 0.84))
    if int(retrieval_deficit.get("academic_deficit") or 0) > 0:
        specs.append(("paper arxiv study research", "academic_deficit", ["academic", "pdf"], 0.82))
    if not specs:
        specs.extend([
            ("official report source", "valid_source_deficit", ["official", "report"], 0.78),
            ("market outlook analysis evidence", "evidence_deficit", ["report", "news"], 0.72),
        ])
    queries: list[dict] = []
    seen: set[str] = set()
    for suffix, purpose_detail, preferred, priority in specs:
        q = " ".join(f"{anchor} {suffix}".split())
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append({
            "query": q,
            "purpose": "replenish_failed_sources",
            "purpose_detail": purpose_detail,
            "source_profile": profile,
            "preferred_source_types": preferred,
            "exclude_domains": exclude_domains,
            "exclusion_terms": exclusion_terms,
            "preferred_engines": engines(),
            "avoid_engines": suspended,
            "priority": priority,
        })
    return queries[:12]

def build_report_outline(intent: dict[str, Any], focused_research_plan: dict[str, Any] | None = None) -> list[str]:
    kind = str(intent.get("expected_output_type") or "report")
    if kind == "market_analysis":
        return ["Executive Summary", "市場概況", "主要ドライバー", "技術動向", "主要プレイヤー", "政策・規制", "投資・提携", "リスク・制約", "今後12〜36か月の見通し", "根拠と不確実性", "追加調査項目"]
    if kind == "technical_survey":
        return ["要約", "技術概要", "研究動向", "性能指標", "課題", "主要研究機関/企業", "実用化状況", "参考文献"]
    if kind == "official_source_review":
        return ["公式発表要約", "政策/規制", "対象範囲", "数値/期限/制度", "影響", "未確認点"]
    return ["要約", "背景", "主要論点", "根拠", "不確実性", "追加調査項目"]


def build_source_mix(sources: list[dict[str, Any]], evidence_chunks: list[dict[str, Any]] | None = None) -> dict[str, int]:
    mix = {"official": 0, "report_pdf": 0, "recent_news": 0, "academic": 0, "company_ir": 0, "industry_association": 0}
    for item in sources:
        stype = classify_source_type(item)
        url = str(item.get("url") or item.get("final_url") or "").lower()
        if stype == "official" or item.get("is_official"):
            mix["official"] += 1
        if stype in {"pdf", "report"} or item.get("is_pdf") or url.endswith(".pdf"):
            mix["report_pdf"] += 1
        if stype == "news":
            mix["recent_news"] += 1
        if stype == "academic":
            mix["academic"] += 1
        if stype == "company_ir":
            mix["company_ir"] += 1
        if stype == "industry_association":
            mix["industry_association"] += 1
    return mix


def build_coverage_matrix(plan: dict[str, Any], evidence_chunks: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    dims = list(plan.get("must_cover_dimensions") or [])
    source_lookup = {str(s.get("source_id") or s.get("id") or ""): s for s in sources or []}
    rows = []
    for dim in dims:
        kws = _DIMENSION_KEYWORDS.get(dim, [dim.replace("_", " ")])
        matches = []
        best = []
        for chunk in evidence_chunks or []:
            text = f"{chunk.get('title','')} {chunk.get('quote','')} {chunk.get('text','')} {chunk.get('snippet','')}".lower()
            if any(kw.lower() in text for kw in kws):
                matches.append(chunk)
                label = str(chunk.get("citation_label") or chunk.get("source_label") or "")
                if not label:
                    sid = str(chunk.get("source_id") or "")
                    label = str(source_lookup.get(sid, {}).get("citation_label") or sid)
                if label and label not in best:
                    best.append(label)
        count = len(matches)
        status = "covered" if count >= 3 else "weak" if count >= 1 else "missing"
        rows.append({"dimension": dim, "status": status, "evidence_count": count, "best_sources": best[:5], "notes": "十分な根拠があります。" if status == "covered" else "根拠が限定的です。" if status == "weak" else "該当根拠が不足しています。"})
    return rows
