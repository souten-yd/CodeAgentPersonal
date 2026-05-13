from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime, timezone
import json
import re
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from app.nexus.answer_builder import build_answer_payload
from app.nexus.citation_mapper import build_citation_map, normalize_reference_labels
from app.nexus.config import load_runtime_config
from app.nexus.downloader import safe_download, save_download_artifacts
from app.nexus.evidence import EvidenceItem, replace_evidence_items_for_job, save_evidence_items
from app.nexus.jobs import append_job_event, append_job_heartbeat, create_job, ensure_job_exists, update_job
from app.nexus.news_sources import NewsResearchSourceProfile, collect_news_research_sources, convert_news_items_to_evidence
from app.nexus.research_gaps import analyze_claim_level_gaps
from app.nexus.source_collector import build_curated_direct_source_candidates, build_dynamic_direct_source_candidates, classify_retrieval_failure, collect_source_candidates, extract_dynamic_topic_anchors_from_screening, get_curated_domain_hints, rank_source_candidates
from app.nexus.research_planner import (
    build_coverage_matrix,
    build_focused_research_plan,
    build_replenishment_queries,
    build_report_outline,
    build_source_mix,
    classify_source_type,
    get_screening_settings,
    infer_research_intent,
    summarize_screening_candidates,
)
from app.nexus.source_registry import (
    canonicalize_source_url,
    find_reusable_artifact,
    register_or_update_sources,
    upsert_source_artifact,
)
from app.nexus.db import get_conn
from app.nexus.web_scout import EngineHealthTracker, choose_replacement_engines, plan_web_queries, resolve_searxng_engines_for_profile, run_web_search


RESEARCH_STATES = (
    "queued",
    "planning",
    "searching",
    "collecting_sources",
    "downloading",
    "extracting",
    "ingesting_to_library",
    "retrieving_evidence",
    "answering",
    "verifying",
    "reporting",
    "completed",
    "failed",
    "cancelled",
)
REPORTING_TIMEOUT_SEC = 120
EXHAUSTIVE_REPORTING_TIMEOUT_SEC = 180


@dataclass
class ResearchAgentInput:
    query: str
    project: str = "default"
    mode: str = "standard"
    depth: str | None = None
    max_queries: int | None = None
    max_results_per_query: int | None = None
    max_sources: int | None = None
    max_downloads: int | None = None
    max_download_mb: int | None = None
    max_total_download_mb: int | None = None
    scope: str | list[str] | None = None
    language: str | None = None
    manual_urls: list[str] | None = None
    prefer_pdf: bool = True
    official_first: bool = True
    download_timeout_sec: int | None = None
    continue_on_download_error: bool = True
    recursive_search: bool = False
    max_iterations: int = 1
    max_followup_queries: int = 4
    confidence_threshold: float = 0.75
    stop_when_sufficient: bool = True
    source_profile: str = "web"
    target_candidate_count: int | None = None
    target_valid_source_count: int | None = None
    target_evidence_count: int | None = None
    target_high_quality_source_count: int | None = None
    target_official_source_count: int | None = None
    target_pdf_source_count: int | None = None
    max_retrieval_rounds: int | None = None
    adaptive_retrieval_enabled: bool | None = None
    news_budget: dict[str, Any] | None = None
    replenishment_enabled: bool = True
    target_replacement_ratio: float = 1.0
    max_replenishment_rounds: int | None = None
    max_replenishment_candidates: int | None = None
    max_replenishment_downloads: int | None = None
    min_valid_source_count: int | None = None
    min_evidence_count: int | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()




_RETRIEVAL_TARGET_DEFAULTS: dict[str, dict[str, Any]] = {
    "quick": {"target_candidate_count": 40, "target_valid_source_count": 8, "target_evidence_count": 25, "target_high_quality_source_count": 0, "target_official_source_count": 0, "target_pdf_source_count": 0, "max_retrieval_rounds": 1, "adaptive_retrieval_enabled": True, "max_replenishment_rounds": 1, "max_replenishment_candidates": 20, "max_replenishment_downloads": 10},
    "standard": {"target_candidate_count": 120, "target_valid_source_count": 25, "target_evidence_count": 80, "target_high_quality_source_count": 0, "target_official_source_count": 0, "target_pdf_source_count": 0, "max_retrieval_rounds": 2, "adaptive_retrieval_enabled": True, "max_replenishment_rounds": 1, "max_replenishment_candidates": 40, "max_replenishment_downloads": 20},
    "deep": {"target_candidate_count": 300, "target_valid_source_count": 60, "target_evidence_count": 180, "target_high_quality_source_count": 16, "target_official_source_count": 8, "target_pdf_source_count": 8, "max_retrieval_rounds": 4, "adaptive_retrieval_enabled": True, "max_replenishment_rounds": 3, "max_replenishment_candidates": 120, "max_replenishment_downloads": 40},
    "exhaustive": {"target_candidate_count": 500, "target_valid_source_count": 100, "target_evidence_count": 300, "target_high_quality_source_count": 24, "target_official_source_count": 14, "target_pdf_source_count": 14, "max_retrieval_rounds": 6, "adaptive_retrieval_enabled": True, "max_replenishment_rounds": 5, "max_replenishment_candidates": 220, "max_replenishment_downloads": 80},
}


def build_retrieval_targets(payload: ResearchAgentInput, *, long_64k: bool = False) -> dict[str, Any]:
    depth = str(payload.depth or payload.mode or "standard").strip().lower()
    if depth not in _RETRIEVAL_TARGET_DEFAULTS:
        depth = "standard"
    targets = dict(_RETRIEVAL_TARGET_DEFAULTS[depth])
    if long_64k and depth == "deep":
        targets["target_evidence_count"] = 120
    if long_64k and depth == "exhaustive":
        targets["target_evidence_count"] = 180
    for key in list(targets):
        value = getattr(payload, key, None)
        if value is not None:
            targets[key] = value
    if payload.min_valid_source_count is not None and payload.target_valid_source_count is None:
        targets["target_valid_source_count"] = payload.min_valid_source_count
    if payload.min_evidence_count is not None and payload.target_evidence_count is None:
        targets["target_evidence_count"] = payload.min_evidence_count
    targets["replenishment_enabled"] = bool(getattr(payload, "replenishment_enabled", True))
    targets["target_replacement_ratio"] = float(getattr(payload, "target_replacement_ratio", 1.0) or 1.0)
    return targets


def compute_recursive_download_budget(depth: str, max_downloads: int) -> dict[str, int]:
    import math
    depth_key = str(depth or "standard").strip().lower()
    total = max(0, int(max_downloads or 0))
    reserved = 0
    if depth_key == "deep":
        reserved = max(20, int(math.ceil(total * 0.25)))
    elif depth_key == "exhaustive":
        reserved = max(50, int(math.ceil(total * 0.30)))
    reserved = min(total, reserved)
    return {"initial_download_limit": max(0, total - reserved), "recursive_reserved_downloads": reserved}


def should_auto_expand_download_budget(summary: dict, targets: dict, unresolved_items: list[dict] | None = None) -> bool:
    skipped = int(summary.get("skipped_due_to_download_limit_count") or 0)
    if skipped <= 0:
        return False
    unresolved = bool(unresolved_items or summary.get("unresolved_items") or [])
    return (
        int(summary.get("valid_source_count") or 0) < int(targets.get("target_valid_source_count") or 0)
        or int(summary.get("evidence_count") or 0) < int(targets.get("target_evidence_count") or 0)
        or unresolved
    )


def should_expand_retrieval(summary: dict, targets: dict, round_index: int) -> tuple[bool, list[str]]:
    max_rounds = int(targets.get("max_retrieval_rounds") or 1)
    if round_index >= max_rounds:
        return False, []
    checks = [
        ("valid_source_count", "target_valid_source_count", "valid_sources_below_target"),
        ("evidence_count", "target_evidence_count", "evidence_below_target"),
        ("high_quality_source_count", "target_high_quality_source_count", "high_quality_sources_below_target"),
        ("official_source_count", "target_official_source_count", "official_sources_below_target"),
        ("pdf_source_count", "target_pdf_source_count", "pdf_sources_below_target"),
        ("candidate_count", "target_candidate_count", "candidate_pool_below_target"),
    ]
    reasons: list[str] = []
    for current_key, target_key, reason in checks:
        target_value = int(targets.get(target_key) or 0)
        if target_value > 0 and int(summary.get(current_key) or 0) < target_value:
            reasons.append(reason)
    return bool(reasons), reasons



def _collect_failed_retrieval_items(candidates: list[dict] | None = None, sources: list[dict] | None = None) -> list[dict]:
    failed: list[dict] = []
    for item in list(candidates or []) + list(sources or []):
        failure_class = classify_retrieval_failure(item)
        status = str(item.get("status") or "").lower()
        if failure_class != "unknown" or status in {"failed", "degraded", "off_topic", "duplicate", "skipped_download_limit", "skipped_size_limit"}:
            failed.append({**item, "failure_class": failure_class})
    return failed


def compute_retrieval_deficit(summary: dict, targets: dict) -> dict:
    """Compute source/evidence/source-mix gaps that should drive replenishment."""
    target_valid = int(targets.get("target_valid_source_count") or targets.get("min_valid_source_count") or 0)
    target_evidence = int(targets.get("target_evidence_count") or targets.get("min_evidence_count") or 0)
    valid_deficit = max(0, target_valid - int(summary.get("valid_source_count") or 0))
    evidence_deficit = max(0, target_evidence - int(summary.get("evidence_count") or 0))
    source_mix = dict(summary.get("source_mix") or {})
    source_mix_targets = dict(summary.get("source_mix_targets") or targets.get("source_mix_targets") or {})

    def mix_deficit(*keys: str) -> int:
        return max((max(0, int(source_mix_targets.get(key) or 0) - int(source_mix.get(key) or 0)) for key in keys), default=0)

    failed_items = list(summary.get("failed_sources") or summary.get("failed_candidates") or [])
    if not failed_items and int(summary.get("failed_candidate_count") or 0) > 0:
        failed_count = int(summary.get("failed_candidate_count") or 0)
    else:
        failure_classes = [classify_retrieval_failure(item) for item in failed_items]
        failed_count = sum(1 for cls in failure_classes if cls not in {"unknown", "skipped_limit"})
        skipped_limit_count = sum(1 for cls in failure_classes if cls == "skipped_limit")
        failed_count += skipped_limit_count
        duplicate_count = sum(1 for cls in failure_classes if cls == "duplicate")
        if duplicate_count > 1:
            failed_count -= duplicate_count - max(1, duplicate_count // 2)
        quality_failure_count = max(0, failed_count - skipped_limit_count)
    ratio = float(targets.get("target_replacement_ratio") or 1.0)
    max_candidates = int(targets.get("max_replenishment_candidates") or 0)
    replacement_target = max(valid_deficit, int(__import__("math").ceil(failed_count * ratio)))
    if max_candidates > 0:
        replacement_target = min(replacement_target, max_candidates)
    deficits = {
        "valid_source_deficit": valid_deficit,
        "evidence_deficit": evidence_deficit,
        "official_deficit": max(int(targets.get("target_official_source_count") or 0) - int(summary.get("official_source_count") or 0), mix_deficit("official"), 0),
        "pdf_deficit": max(int(targets.get("target_pdf_source_count") or 0) - int(summary.get("pdf_source_count") or 0), mix_deficit("report_pdf"), 0),
        "fresh_news_deficit": mix_deficit("recent_news", "news_recent"),
        "company_ir_deficit": mix_deficit("company_ir"),
        "academic_deficit": mix_deficit("academic"),
        "failed_candidate_count": max(0, failed_count),
        "replacement_target_count": max(0, replacement_target),
        "source_mix_deficits": {key: max(0, int(source_mix_targets.get(key) or 0) - int(source_mix.get(key) or 0)) for key in source_mix_targets},
    }
    if "quality_failure_count" not in locals():
        quality_failure_count = failed_count
    deficits["replacement_needed"] = bool(deficits["replacement_target_count"] > 0 and (valid_deficit > 0 or evidence_deficit > 0 or any(v > 0 for v in deficits["source_mix_deficits"].values()) or quality_failure_count > 0))
    return deficits

def build_retrieval_strategy(source_profile: str, depth: str, round_index: int, gaps: dict | None = None) -> dict:
    profile = str(source_profile or "web").strip().lower()
    strategies = ["safe_research", "official_pdf_report", "curated_domains", "broad_safe_fallback", "claim_gap_followup"]
    name = strategies[min(max(round_index, 0), len(strategies) - 1)]
    query_suffixes: list[str] = []
    use_curated_domains = False
    if name == "official_pdf_report":
        query_suffixes = ["official", "PDF", "report", "white paper", "market report", "government", "industry association", "公式", "PDF", "報告書", "白書", "市場調査", "業界団体", "官公庁"]
    elif name == "curated_domains":
        use_curated_domains = True
        query_suffixes = ["official report", "technical report", "industry association", "annual report"]
    elif name == "broad_safe_fallback":
        query_suffixes = ["analysis", "outlook", "forecast", "roadmap", "risks opportunities", "latest", "事例", "動向", "見通し"]
    elif name == "claim_gap_followup":
        query_suffixes = ["evidence", "source", "data", "statistics", "根拠", "統計", "データ"]
    return {
        "name": name,
        "searxng_engine_profile": "adaptive_research" if round_index > 0 else "safe_research",
        "query_suffixes": query_suffixes,
        "use_curated_domains": use_curated_domains,
        "source_profile": profile,
        "depth": depth,
        "gaps": gaps or {},
    }


def _retrieval_strategy_queries(base_queries: list[str], strategy: dict, query: str, source_profile: str, cap: int) -> list[str]:
    queries: list[str] = []
    for q in base_queries or [query]:
        if q and q not in queries:
            queries.append(q)
    for suffix in strategy.get("query_suffixes") or []:
        variant = f"{query} {suffix}".strip()
        if variant not in queries:
            queries.append(variant)
    if strategy.get("use_curated_domains"):
        for hint in get_curated_domain_hints(query, source_profile)[:24]:
            variant = f"{query} {hint}".strip()
            if variant not in queries:
                queries.append(variant)
    return queries[: max(1, cap)]


def _retrieval_summary(
    *,
    targets: dict,
    retrieval_rounds: list[dict],
    candidate_count: int,
    attempted_download_count: int,
    registered_sources: list[dict],
    evidence_chunks: list[dict],
    skipped_due_to_download_limit_count: int,
    intent: dict | None = None,
    screening_summary: dict | None = None,
    focused_research_plan: dict | None = None,
    coverage_matrix: list[dict] | None = None,
    search_policy: dict | None = None,
    curated_direct_candidate_count: int = 0,
    curated_direct_downloaded_count: int = 0,
    curated_direct_domains: list[str] | None = None,
    static_curated_direct_candidate_count: int | None = None,
    dynamic_curated_direct_candidate_count: int = 0,
    dynamic_curated_direct_domains: list[str] | None = None,
    dynamic_screening_registry: dict | None = None,
    engine_health: dict | None = None,
    engine_replenishment: dict | None = None,
) -> dict[str, Any]:
    def _url(item: dict) -> str:
        return str(item.get("url") or item.get("final_url") or "").lower()
    valid = [s for s in registered_sources if str(s.get("status") or "") in {"downloaded", "degraded", "reused", "ingested", ""}]
    official_count = sum(1 for s in valid if s.get("is_official") or any(token in _url(s) for token in (".gov", ".go.jp", ".europa.eu", ".int", ".edu", ".ac.jp", "nasa.gov", "faa.gov", "easa.europa.eu", "icao.int", "iata.org")))
    pdf_count = sum(1 for s in valid if s.get("is_pdf") or "pdf" in str(s.get("content_type") or "").lower() or _url(s).endswith(".pdf"))
    high_quality = sum(1 for s in valid if s.get("is_official") or s.get("is_pdf") or float(s.get("retrieval_score") or s.get("source_score") or 0) >= 3.0)
    fresh_count = sum(1 for s in valid if str(s.get("freshness_bucket") or "").lower() == "fresh" or float(s.get("freshness_score") or 0) >= 0.65)
    stale_count = sum(1 for s in valid if str(s.get("freshness_bucket") or "").lower() == "stale" or float(s.get("freshness_score") or 1) < 0.2)
    policy = dict(search_policy or {})
    if not policy:
        inferred_profile = str((intent or {}).get("source_profile") or "general")
        policy = resolve_searxng_engines_for_profile(inferred_profile, str((intent or {}).get("depth") or "standard"), str((intent or {}).get("time_horizon") or "balanced"))
    summary = {
        "retrieval_rounds": retrieval_rounds,
        "candidate_count": candidate_count,
        "attempted_download_count": attempted_download_count,
        "valid_source_count": len(valid),
        "evidence_count": len(evidence_chunks),
        "high_quality_source_count": high_quality,
        "official_source_count": official_count,
        "pdf_source_count": pdf_count,
        "skipped_due_to_download_limit_count": skipped_due_to_download_limit_count,
        "source_profile": policy.get("source_profile"),
        "engine_priority": policy.get("engine_priority"),
        "searxng_engines": policy.get("searxng_engines"),
        "freshness_policy": policy.get("freshness_policy"),
        "fresh_source_count": fresh_count,
        "stale_source_count": stale_count,
        "curated_direct_candidate_count": max(0, int(curated_direct_candidate_count)),
        "static_curated_direct_candidate_count": max(0, int(static_curated_direct_candidate_count if static_curated_direct_candidate_count is not None else curated_direct_candidate_count - dynamic_curated_direct_candidate_count)),
        "dynamic_curated_direct_candidate_count": max(0, int(dynamic_curated_direct_candidate_count)),
        "curated_direct_downloaded_count": max(0, int(curated_direct_downloaded_count)),
        "curated_direct_domains": list(curated_direct_domains or []),
        "dynamic_curated_direct_domains": list(dynamic_curated_direct_domains or []),
        "dynamic_screening_registry": dynamic_screening_registry or {},
        "dynamic_anchor_entities": list((dynamic_screening_registry or {}).get("entities") or []),
        "dynamic_anchor_domains": list((dynamic_screening_registry or {}).get("domains") or []),
    }
    summary.update({
        "broad_web_enabled": policy.get("broad_web_enabled", False),
        "broad_web_engines": policy.get("broad_web_engines", []),
        "suspended_engines": [],
        "engine_failures": {},
        "fallback_to_safe_engines": False,
    })
    summary.update(engine_health or {})
    summary["engine_replenishment"] = engine_replenishment or {"enabled": bool(targets.get("replenishment_enabled", True)), "attempted": False, "replacement_queries": 0, "replacement_candidates": 0, "replacement_downloads": 0, "replacement_valid_sources": 0, "suspended_engines": list((engine_health or {}).get("suspended_engines") or []), "fallback_to_safe_engines": bool((engine_health or {}).get("fallback_to_safe_engines", False)), "replenishment_rounds": [], "source_mix_deficits": {}, "max_replenishment_downloads": 0, "replenishment_download_attempts_used": 0, "replenishment_download_budget_remaining": 0}
    summary.update({k: targets.get(k) for k in targets if k.startswith("target_") or k in {"max_retrieval_rounds", "adaptive_retrieval_enabled"}})
    _, unsatisfied = should_expand_retrieval(summary, {**targets, "max_retrieval_rounds": 999}, 0)
    summary["targets_satisfied"] = not unsatisfied
    summary["unsatisfied_targets"] = unsatisfied
    source_mix = build_source_mix(valid, evidence_chunks)
    source_mix_targets = dict((focused_research_plan or {}).get("source_mix_targets") or {})
    unsatisfied_mix = [key for key, target in source_mix_targets.items() if int(source_mix.get(key, 0)) < int(target or 0)]
    summary.update({
        "intent": intent or {},
        "screening_summary": screening_summary or {},
        "focused_research_plan": focused_research_plan or {},
        "source_mix": source_mix,
        "source_mix_targets": source_mix_targets,
        "source_mix_satisfied": not unsatisfied_mix,
        "unsatisfied_source_mix": unsatisfied_mix,
        "coverage_matrix": coverage_matrix or [],
    })
    return summary


def _screening_candidates_from_search_items(items: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        canonical = canonicalize_source_url(url) or url
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        row = {
            "url": canonical,
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("snippet") or ""),
            "domain": re.sub(r"^www\.", "", urlparse(canonical).netloc.lower()),
            "publishedDate": str(item.get("published_at") or item.get("published_date") or item.get("age") or ""),
            "engine": str(item.get("engine") or item.get("provider") or ""),
            "provider": str(item.get("provider") or ""),
            "source_type": str(item.get("source_type") or "web"),
            "screening_stage": "broad_screening",
        }
        row["source_type"] = classify_source_type(row)
        candidates.append(row)
    return candidates


def run_broad_screening(
    intent: dict,
    *,
    target_screening_candidates: int,
    max_screening_queries: int,
    max_results_per_query: int,
) -> dict:
    topic = str(intent.get("normalized_topic") or intent.get("original_query") or "").strip()
    base_queries = plan_web_queries(topic, mode="deep", depth="deep", max_queries=max_screening_queries, scope=intent.get("source_profile"), language=intent.get("language"), source_profile=str(intent.get("source_profile") or "general"))
    dimension_queries = [f"{topic} {dim.replace('_', ' ')}" for dim in intent.get("required_dimensions") or []]
    queries: list[str] = []
    for q in [*base_queries, *dimension_queries]:
        q = " ".join(str(q).split())
        if q and q not in queries:
            queries.append(q)
        if len(queries) >= max_screening_queries:
            break
    search = run_web_search(queries, mode="deep", depth="deep", max_results_per_query=max_results_per_query, scope=intent.get("source_profile"), language=intent.get("language"), source_profile=str(intent.get("source_profile") or "general"), freshness=str(intent.get("time_horizon") or "balanced"))
    raw_items = list(search.get("items") or [])
    candidates = _screening_candidates_from_search_items(raw_items)[:target_screening_candidates]
    summary = summarize_screening_candidates(candidates, intent)
    payload = {
        "target_screening_candidates": target_screening_candidates,
        "screening_query_count": len(queries),
        "raw_candidate_count": len(raw_items),
        "unique_candidate_count": len(candidates),
        "domain_count": summary.get("domain_count", 0),
        "fresh_candidate_count": int((summary.get("freshness_counts") or {}).get("current_year", 0)) + int((summary.get("freshness_counts") or {}).get("last_12_months", 0)),
        "official_candidate_count": int((summary.get("source_type_counts") or {}).get("official", 0)),
        "pdf_candidate_count": int((summary.get("source_type_counts") or {}).get("pdf", 0)),
        "academic_candidate_count": int((summary.get("source_type_counts") or {}).get("academic", 0)),
    }
    return {"queries": queries, "search": search, "candidates": candidates, "summary": summary, "payload": payload}


def _select_download_candidates(ranked_candidates: list[dict], attempted: set[str], max_count: int, source_mix_targets: dict | None = None, source_mix_deficits: dict | None = None) -> list[dict]:
    if max_count <= 0:
        return []
    selected: list[dict] = []
    domain_counts: dict[str, int] = {}
    targets = dict(source_mix_targets or {})
    deficits = dict(source_mix_deficits or {})
    if deficits:
        nested = deficits.get("source_mix_deficits") if isinstance(deficits.get("source_mix_deficits"), dict) else deficits
        for deficit_key, target_key in (("official_deficit", "official"), ("pdf_deficit", "report_pdf"), ("fresh_news_deficit", "recent_news"), ("company_ir_deficit", "company_ir"), ("academic_deficit", "academic")):
            if int(deficits.get(deficit_key) or 0) > 0:
                targets[target_key] = max(int(targets.get(target_key) or 0), int(deficits.get(deficit_key) or 0))
        for key, value in dict(nested or {}).items():
            if int(value or 0) > 0:
                targets[key] = max(int(targets.get(key) or 0), int(value or 0))
    wanted_order = ["official", "report_pdf", "recent_news", "academic", "company_ir", "industry_association"]

    def bucket(candidate: dict) -> str:
        stype = classify_source_type(candidate)
        if stype == "official" or candidate.get("is_official"):
            return "official"
        if stype in {"pdf", "report"} or candidate.get("is_pdf"):
            return "report_pdf"
        if stype == "news":
            return "recent_news"
        if stype == "academic":
            return "academic"
        if stype == "company_ir":
            return "company_ir"
        if stype == "industry_association":
            return "industry_association"
        return "other"

    def try_add(candidate: dict) -> bool:
        canonical = canonicalize_source_url(str(candidate.get("url") or "")) or str(candidate.get("url") or "")
        if not canonical or canonical in attempted or any((canonicalize_source_url(str(x.get("url") or "")) or str(x.get("url") or "")) == canonical for x in selected):
            return False
        domain = urlparse(canonical).netloc.lower()
        if domain and domain_counts.get(domain, 0) >= (4 if candidate.get("is_official") else 3):
            return False
        selected.append(candidate)
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        return True

    for key in wanted_order:
        need = min(int(targets.get(key) or 0), max_count - len(selected))
        if need <= 0:
            continue
        added = 0
        for candidate in ranked_candidates:
            if bucket(candidate) == key and try_add(candidate):
                added += 1
                if added >= need or len(selected) >= max_count:
                    break
        if len(selected) >= max_count:
            break
    for candidate in ranked_candidates:
        if len(selected) >= max_count:
            break
        try_add(candidate)
    return selected



def _determine_final_research_outcome(*, retrieval_summary: dict[str, Any] | None, registered_sources: list[dict] | None, evidence_chunks: list[dict] | None, answer_payload: dict[str, Any] | None, download_error_count: int, source_has_degraded_or_failed: bool) -> dict[str, Any]:
    summary = retrieval_summary or {}
    sources = list(registered_sources or [])
    chunks = list(evidence_chunks or [])
    answer = answer_payload or {}
    generation_mode = str(answer.get("generation_mode") or ((answer.get("generation") or {}).get("mode") if isinstance(answer.get("generation"), dict) else "") or "").strip().lower()
    answer_generated = bool(answer.get("answer_generated")) or generation_mode in {"llm_answer", "llm_answer_truncated"}
    unresolved_count = len(list(answer.get("unresolved_items") or []))
    citation_issues = len(list(((answer.get("citation_verification") or {}).get("warnings") if isinstance(answer.get("citation_verification"), dict) else []) or []))
    valid_source_count = int(summary.get("valid_source_count") or 0)
    evidence_count = int(summary.get("evidence_count") or 0)
    targets_satisfied = summary.get("targets_satisfied")

    if valid_source_count <= 0 or len(sources) <= 0:
        return {"status": "failed", "reason": "no_sources", "phase": "no_sources", "message": "検索結果を取得できませんでした。検索エンジン設定、SearXNG疎通、またはクエリを確認してください。"}
    if evidence_count <= 0 or len(chunks) <= 0:
        return {"status": "degraded", "reason": "no_evidence", "phase": "no_evidence", "message": "根拠を抽出できませんでした。対象ソースの本文取得や抽出設定を確認してください。"}
    if generation_mode == "template_fallback" and valid_source_count <= 0:
        return {"status": "failed", "reason": "no_sources", "phase": "no_sources", "message": "検索結果を取得できませんでした。検索エンジン設定、SearXNG疎通、またはクエリを確認してください。"}
    if targets_satisfied is False:
        return {"status": "degraded", "reason": "targets_unsatisfied", "phase": "completed", "message": "research completed with unmet retrieval targets"}
    if answer_generated and (unresolved_count > 0 or citation_issues > 0):
        return {"status": "degraded", "reason": "finalization_warnings", "phase": "completed", "message": "research completed with verification warnings"}
    if download_error_count > 0 or source_has_degraded_or_failed:
        return {"status": "degraded", "reason": "degraded_sources", "phase": "completed", "message": "research completed with degraded sources"}
    return {"status": "completed", "reason": "", "phase": "completed", "message": "research completed"}
def _extract_http_status(exc: Exception) -> int | None:
    candidates: list[Exception | BaseException] = [exc]
    seen: set[int] = set()
    while candidates:
        current = candidates.pop(0)
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)

        code = getattr(current, "code", None)
        if isinstance(code, int):
            return code
        status = getattr(current, "status", None)
        if isinstance(status, int):
            return status

        message = str(current)
        match = re.search(r"\bhttp\s+(\d{3})\b", message, re.IGNORECASE)
        if match:
            return int(match.group(1))

        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if cause is not None:
            candidates.append(cause)
        if context is not None:
            candidates.append(context)
    return None


def _is_body_shortage_error(exc: Exception) -> bool:
    text = str(exc).lower()
    keywords = (
        "本文不足",
        "body shortage",
        "insufficient body",
        "empty body",
        "empty content",
        "no content",
        "no evidence",
        "evidence not found",
    )
    return any(keyword in text for keyword in keywords)


def _load_source_chunks(source_ids: list[str]) -> list[dict]:
    normalized = [s for s in source_ids if s]
    if not normalized:
        return []
    placeholders = ",".join("?" for _ in normalized)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT sc.source_id, sc.chunk_id, sc.page_start, sc.page_end, sc.citation_label,
                   c.title AS title, c.text AS quote
            FROM nexus_source_chunks sc
            LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
            WHERE sc.source_id IN ({placeholders})
            ORDER BY sc.created_at ASC, sc.id ASC
            """,
            tuple(normalized),
        ).fetchall()
    return [dict(row) for row in rows]
def _record_state(job_id: str, state: str, *, message: str, progress: float) -> None:
    append_job_event(
        job_id,
        "state_transition",
        {
            "state": state,
            "status": "running",
            "phase": state,
            "message": message,
            "progress": progress,
            "updated_at": _now_iso(),
        },
    )
    append_job_heartbeat(job_id, state, message, progress, {"state": state})


def _emit_phase(
    job_id: str,
    event_type: str,
    *,
    phase: str,
    message: str,
    progress: float | None = None,
    details: dict | None = None,
    status: str = "running",
) -> None:
    payload = {
        "status": status,
        "phase": phase,
        "message": message,
        "progress": progress,
        "updated_at": _now_iso(),
    }
    if details:
        payload["details"] = details
    append_job_event(job_id, event_type, payload)
    if status == "running":
        append_job_heartbeat(job_id, phase, message, progress, details or {})


def _build_evidence_from_sources(job_id: str, sources: list[dict]) -> list[EvidenceItem]:
    source_ids = [str(item.get("source_id") or "").strip() for item in sources]
    source_ids = [source_id for source_id in source_ids if source_id]
    if not source_ids:
        return []

    placeholders = ",".join("?" for _ in source_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT s.source_id, s.source_type, s.url, s.final_url, s.title, s.publisher, s.retrieved_at,
                   s.linked_document_id, sc.chunk_id, sc.citation_label, c.text AS quote
            FROM nexus_sources s
            LEFT JOIN nexus_source_chunks sc ON sc.source_id = s.source_id
            LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
            WHERE s.source_id IN ({placeholders})
            ORDER BY s.created_at ASC, sc.id ASC
            """,
            tuple(source_ids),
        ).fetchall()

    evidence: list[EvidenceItem] = []
    seen_chunk_keys: set[tuple[str, str]] = set()

    for row in rows:
        source_id = str(row["source_id"] or "")
        chunk_id = str(row["chunk_id"] or "").strip()
        linked_document_id = str(row["linked_document_id"] or "")
        if chunk_id:
            dedupe_key = (source_id, chunk_id)
            if dedupe_key in seen_chunk_keys:
                continue
            seen_chunk_keys.add(dedupe_key)
            evidence.append(
                EvidenceItem(
                    source_id=source_id,
                    source_type=str(row["source_type"] or "web"),
                    document_id=linked_document_id,
                    chunk_id=chunk_id,
                    url=str(row["final_url"] or row["url"] or ""),
                    retrieved_at=str(row["retrieved_at"] or _now_iso()),
                    title=str(row["title"] or ""),
                    publisher=str(row["publisher"] or ""),
                    citation_label=str(row["citation_label"] or ""),
                    note=f"source:{source_id}",
                    quote=str(row["quote"] or ""),
                    metadata_json={"source_id": source_id, "linked_document_id": linked_document_id},
                )
            )

    if not evidence:
        for source in sources:
            source_id = str(source.get("source_id") or "").strip()
            if not source_id:
                continue
            evidence.append(
                EvidenceItem(
                    source_id=source_id,
                    source_type=str(source.get("source_type") or "web"),
                    document_id=str(source.get("linked_document_id") or ""),
                    chunk_id=f"{source_id}:fallback",
                    url=str(source.get("final_url") or source.get("url") or ""),
                    retrieved_at=str(source.get("retrieved_at") or _now_iso()),
                    title=str(source.get("title") or ""),
                    publisher=str(source.get("publisher") or ""),
                    citation_label=f"[S{len(evidence) + 1}]",
                    note="fallback_without_chunks",
                    quote=str(source.get("snippet") or ""),
                    metadata_json={"source_id": source_id, "fallback": True},
                )
            )
    return evidence


def _analyze_research_gaps(*, sources: list[dict], evidence_chunks: list[dict], answer_payload: dict) -> dict:
    source_count = len(sources)
    evidence_chunk_count = len(evidence_chunks)
    has_official_or_pdf = any(bool(s.get("is_official")) or "pdf" in str(s.get("content_type") or "").lower() for s in sources)
    answer_text = str(answer_payload.get("answer_markdown") or answer_payload.get("summary") or "")
    unverified_mentions = answer_text.count("未確認")
    degraded_or_failed = sum(1 for s in sources if str(s.get("status") or "") in {"degraded", "failed"})
    citation_count = len(answer_payload.get("references") or [])
    failed_ratio = (degraded_or_failed / source_count) if source_count else 1.0

    confidence = 0.0
    confidence += min(0.25, source_count / 20.0)
    confidence += min(0.2, evidence_chunk_count / 25.0)
    confidence += 0.15 if has_official_or_pdf else 0.0
    confidence += min(0.25, citation_count / 12.0)
    confidence -= min(0.25, failed_ratio * 0.25 + (0.1 if unverified_mentions else 0.0))

    claim_analysis = analyze_claim_level_gaps(answer_payload, evidence_chunks, sources)
    support_ratio = float(claim_analysis.get("support_ratio") or 0.0)
    confidence += min(0.20, support_ratio * 0.20)
    confidence -= min(0.12, int(claim_analysis.get("weakly_supported_claim_count") or 0) * 0.02)
    confidence -= min(0.20, int(claim_analysis.get("unsupported_claim_count") or 0) * 0.03)
    confidence -= min(0.10, int(claim_analysis.get("unresolved_claim_count") or 0) * 0.02)
    confidence += min(0.05, float(claim_analysis.get("average_source_quality_score") or 0.0) * 0.05)
    confidence -= min(0.08, int(claim_analysis.get("low_quality_supported_claim_count") or 0) * 0.03)
    confidence -= min(0.12, int(claim_analysis.get("contradiction_count") or 0) * 0.04)
    confidence = max(0.0, min(1.0, confidence))

    gaps: list[str] = []
    unresolved_items: list[str] = []
    if source_count < 3:
        gaps.append("source_count_low")
        unresolved_items.append("信頼できる情報源が不足")
    if evidence_chunk_count < 3:
        gaps.append("evidence_chunks_low")
    if not has_official_or_pdf:
        gaps.append("official_or_pdf_missing")
        unresolved_items.append("一次資料/公式資料が未取得")
    if unverified_mentions > 0:
        gaps.append("answer_contains_unverified")
        unresolved_items.append("未確認の主張が残存")
    if failed_ratio >= 0.4:
        gaps.append("high_degraded_or_failed_ratio")
    if citation_count < 2:
        gaps.append("citation_count_low")
    for gap in claim_analysis.get("gaps") or []:
        if gap not in gaps:
            gaps.append(str(gap))
    for item in claim_analysis.get("unresolved_items") or []:
        if item and item not in unresolved_items:
            unresolved_items.append(str(item))
    return {
        "confidence": confidence,
        "sufficient": len(gaps) == 0,
        "gaps": gaps,
        "unresolved_items": unresolved_items,
        "claim_analysis": claim_analysis,
    }


def _claim_text_for_query(text: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"\[(?:S\d+)\]", " ", str(text or ""))
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[`*_~>#|]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;、。")
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len].rstrip() + "…"


def _generate_claim_followup_queries(original_query: str, claim_analysis: dict, max_queries: int) -> list[str]:
    suffix_by_status = {
        "unsupported": "根拠 一次資料",
        "weakly_supported": "公式資料 検証",
        "unresolved": "未確認 公式 発表",
    }
    queries: list[str] = []
    seen: set[str] = set()
    for claim in (claim_analysis or {}).get("claims") or []:
        if not isinstance(claim, dict):
            continue
        status = str(claim.get("status") or "")
        suffix = suffix_by_status.get(status)
        if not suffix:
            continue
        claim_text = _claim_text_for_query(str(claim.get("claim") or claim.get("text") or ""))
        if not claim_text:
            continue
        query = f"{original_query} {claim_text} {suffix}".strip()
        dedupe_key = re.sub(r"\s+", " ", query).lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries


def _generate_followup_queries(*, original_query: str, gaps: list[str], max_followup_queries: int, claim_analysis: dict | None = None) -> list[str]:
    claim_queries = _generate_claim_followup_queries(original_query, claim_analysis or {}, max_followup_queries)
    if claim_queries:
        return claim_queries[:max_followup_queries]

    gap_hints = {
        "source_count_low": "最新 統計 公式データ",
        "evidence_chunks_low": "詳細 レポート PDF",
        "official_or_pdf_missing": "site:gov OR site:org filetype:pdf",
        "answer_contains_unverified": "検証 ファクトチェック 一次情報",
        "high_degraded_or_failed_ratio": "ミラー 公的機関 代替ソース",
        "citation_count_low": "根拠 出典",
        "weakly_supported_claims": "公式資料 検証",
        "unsupported_claims": "根拠 一次資料 検証",
        "unresolved_claims": "未確認事項 公式 発表",
        "low_evidence_diversity": "independent sources analysis",
    }
    queries: list[str] = []
    seen: set[str] = set()
    for gap in gaps:
        hint = gap_hints.get(gap)
        if not hint:
            continue
        q = f"{original_query} {hint}".strip()
        key = re.sub(r"\s+", " ", q).lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(q)
        if len(queries) >= max_followup_queries:
            break
    return queries


def _should_stop_recursive_research(*, analysis: dict, iteration: int, payload: ResearchAgentInput) -> tuple[bool, str]:
    if analysis.get("confidence", 0.0) >= payload.confidence_threshold and payload.stop_when_sufficient:
        return True, "confidence_threshold_reached"
    if analysis.get("sufficient") and payload.stop_when_sufficient:
        return True, "sufficient_evidence"
    return False, "continue"







def save_minimal_research_answer(
    *,
    job_id: str,
    project: str,
    question: str,
    answer_payload: dict,
) -> str:
    """Persist a minimal research answer row when normal answer building is skipped."""
    answer_id = str(uuid.uuid4())
    answer_markdown = str(
        answer_payload.get("answer_markdown")
        or answer_payload.get("answer")
        or answer_payload.get("summary")
        or ""
    )
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nexus_research_answers(
                answer_id, job_id, project, question,
                answer_markdown, evidence_json, answer_json, source_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                job_id,
                project,
                question,
                answer_markdown,
                "[]",
                json.dumps(answer_payload, ensure_ascii=False),
                "[]",
                _now_iso(),
            ),
        )
        conn.commit()
    return answer_id

def _persist_latest_answer_json(job_id: str, answer_payload: dict) -> None:
    if not job_id or not answer_payload:
        return
    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT answer_id
                FROM nexus_research_answers
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                "UPDATE nexus_research_answers SET answer_json = ? WHERE answer_id = ?",
                (json.dumps(answer_payload, ensure_ascii=False), row["answer_id"]),
            )
            conn.commit()
    except Exception:  # noqa: BLE001
        return


def _candidate_is_stub(candidate: dict) -> bool:
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    return bool(candidate.get("is_stub") or metadata.get("is_stub"))


def _should_filter_stub_sources(payload: ResearchAgentInput) -> bool:
    source_profile = str(getattr(payload, "source_profile", "web") or "web").lower()
    return (
        str(getattr(payload, "mode", "") or "").lower() == "deep"
        or str(getattr(payload, "depth", "") or "").lower() == "deep"
        or bool(getattr(payload, "recursive_search", False))
        or source_profile in {"news", "mixed"}
    )


def _filter_stub_candidates(candidates: list[dict], payload: ResearchAgentInput) -> tuple[list[dict], int]:
    if not _should_filter_stub_sources(payload):
        return candidates, 0
    filtered = [candidate for candidate in candidates if not _candidate_is_stub(candidate)]
    return filtered, len(candidates) - len(filtered)

def _download_progress_payload(*, stats: dict[str, Any], now_iso: str, status: str = "running") -> dict[str, Any]:
    total = max(0, int(stats.get("total", 0)))
    completed = max(0, int(stats.get("completed", 0)))
    progress = (completed / total) if total > 0 else 1.0
    skipped = max(0, int(stats.get("skipped", 0)))
    return {
        "phase": "downloading",
        "status": status,
        "progress": progress,
        "total": total,
        "queued": max(0, total - completed - int(stats.get("active", 0))),
        "active": max(0, int(stats.get("active", 0))),
        "completed": completed,
        "downloaded": max(0, int(stats.get("downloaded", 0))),
        "degraded": max(0, int(stats.get("degraded", 0))),
        "failed": max(0, int(stats.get("failed", 0))),
        "skipped": skipped,
        "total_downloaded_bytes": max(0, int(stats.get("total_downloaded_bytes", 0))),
        "max_total_download_bytes": max(0, int(stats.get("max_total_download_bytes", 0))),
        "updated_at": now_iso,
        "heartbeat_at": now_iso,
    }


def _download_sources_parallel(
    *,
    job_id: str,
    candidates: list[dict],
    max_downloads: int,
    max_download_bytes: int,
    max_total_download_bytes: int,
    download_timeout_sec: int,
    continue_on_download_error: bool,
    concurrency: int,
    pdf_extract_concurrency: int,
    download_progress_interval_sec: int,
    download_stalled_after_sec: int,
) -> tuple[list[dict], int]:
    selected = list(candidates[: max(0, max_downloads)])
    skipped_candidates = list(candidates[max(0, max_downloads) :])
    sources: list[dict] = []
    for candidate in selected:
        source_id = str(candidate.get("source_id") or uuid.uuid4())
        sources.append(
            {
                **candidate,
                "source_id": source_id,
                "final_url": str(candidate.get("url") or ""),
                "status": "queued",
                "error": "",
                "started_at": "",
                "finished_at": "",
                "elapsed_sec": 0.0,
                "size": 0,
                "content_type": "",
                "local_text_path": "",
                "local_markdown_path": "",
                "local_original_path": "",
            }
        )
    for candidate in skipped_candidates:
        source_id = str(candidate.get("source_id") or uuid.uuid4())
        sources.append(
            {
                **candidate,
                "source_id": source_id,
                "final_url": str(candidate.get("url") or ""),
                "status": "skipped_download_limit",
                "error": f"max_downloads exceeded ({max_downloads})",
                "started_at": "",
                "finished_at": _now_iso(),
                "elapsed_sec": 0.0,
                "size": 0,
                "content_type": "",
                "local_text_path": "",
                "local_markdown_path": "",
                "local_original_path": "",
            }
        )

    append_job_event(
        job_id,
        "download_started",
        {
            "status": "running",
            "phase": "downloading",
            "message": "download started",
            "updated_at": _now_iso(),
            "total": len(sources),
            "selected": len(selected),
            "skipped_by_max_downloads": len(skipped_candidates),
        },
    )

    lock = threading.Lock()
    pdf_semaphore = threading.Semaphore(max(1, pdf_extract_concurrency))
    stats: dict[str, Any] = {
        "total": len(sources),
        "active": 0,
        "completed": len(skipped_candidates),
        "downloaded": 0,
        "degraded": 0,
        "failed": 0,
        "skipped": len(skipped_candidates),
        "total_downloaded_bytes": 0,
        "max_total_download_bytes": int(max_total_download_bytes),
    }
    download_error_count = 0
    fatal_errors: list[Exception] = []
    last_completion_at = time.monotonic()
    last_progress_emit_at = 0.0

    def _emit_progress(force: bool = False) -> None:
        nonlocal last_progress_emit_at
        now_monotonic = time.monotonic()
        if not force and (now_monotonic - last_progress_emit_at) < max(1, download_progress_interval_sec):
            return
        now_iso = _now_iso()
        payload = _download_progress_payload(stats=stats, now_iso=now_iso)
        append_job_event(job_id, "download_progress", payload)
        append_job_heartbeat(job_id, "downloading", "download progress", payload["progress"], payload)
        if (
            stats.get("active", 0) > 0
            and (now_monotonic - last_completion_at) >= max(1, download_stalled_after_sec)
        ):
            append_job_event(
                job_id,
                "download_stalled_warning",
                {
                    "status": "running",
                    "phase": "downloading",
                    "message": "一部URLの応答待ち",
                    "active": stats.get("active", 0),
                    "completed": stats.get("completed", 0),
                    "stalled_after_sec": download_stalled_after_sec,
                    "updated_at": now_iso,
                },
            )
        last_progress_emit_at = now_monotonic

    def _worker(source: dict) -> dict:
        started = time.monotonic()
        source["started_at"] = _now_iso()
        source["status"] = "downloading"
        append_job_event(
            job_id,
            "download_source_started",
            {
                "status": "running",
                "phase": "downloading",
                "source_id": source.get("source_id"),
                "url": source.get("url"),
                "title": source.get("title"),
                "domain": source.get("domain"),
                "updated_at": source["started_at"],
            },
        )
        url = str(source.get("url") or "").strip()
        if not url:
            source["status"] = "failed"
            source["error"] = "url is missing"
            source["finished_at"] = _now_iso()
            source["elapsed_sec"] = round(max(0.0, time.monotonic() - started), 3)
            return source
        canonical_url = canonicalize_source_url(url)
        source["canonical_url"] = canonical_url
        reusable = find_reusable_artifact(canonical_url=canonical_url)
        if reusable:
            op = str(reusable.get("local_original_path") or "")
            tp = str(reusable.get("local_text_path") or "")
            mp = str(reusable.get("local_markdown_path") or "")
            if op and tp and mp:
                from pathlib import Path
                if Path(op).exists() and Path(tp).exists() and Path(mp).exists():
                    source["status"] = "reused"
                    source["is_duplicate"] = 1
                    source["duplicate_of_source_id"] = str(reusable.get("source_id") or "")
                    source["local_original_path"] = op
                    source["local_text_path"] = tp
                    source["local_markdown_path"] = mp
                    source["content_sha256"] = str(reusable.get("content_sha256") or "")
                    source["content_type"] = str(reusable.get("content_type") or "")
                    source["final_url"] = str(reusable.get("final_url") or url)
                    return source
        try:
            download_result = safe_download(
                url,
                max_bytes=max_download_bytes,
                connect_timeout_sec=download_timeout_sec,
                read_timeout_sec=download_timeout_sec,
            )
            download_size = int(download_result.get("size") or 0)
            with lock:
                if stats["total_downloaded_bytes"] + download_size > max_total_download_bytes:
                    source["status"] = "skipped_download_limit"
                    source["error"] = "max_total_download_mb exceeded"
                    stats["skipped"] += 1
                else:
                    stats["total_downloaded_bytes"] += download_size
            if source["status"] == "skipped_download_limit":
                source["size"] = download_size
                source["content_type"] = str(download_result.get("content_type") or "")
                source["final_url"] = str(download_result.get("final_url") or url)
                return source

            source["status"] = "extracting"
            saved = save_download_artifacts(
                job_id=job_id,
                source_id=str(source.get("source_id") or ""),
                download_result=download_result,
                pdf_extract_semaphore=pdf_semaphore,
            )
            source["final_url"] = str(download_result.get("final_url") or url)
            source["content_type"] = str(download_result.get("content_type") or "")
            source["size"] = download_size
            source["local_original_path"] = str(saved.get("original") or "")
            source["local_text_path"] = str(saved.get("extracted_txt") or "")
            source["local_markdown_path"] = str(saved.get("extracted_md") or "")
            source["error"] = str(saved.get("error") or "")
            digest = sha256(bytes(download_result.get("bytes") or b"")).hexdigest()
            source["content_sha256"] = digest
            source["canonical_url"] = canonical_url
            dup_artifact = find_reusable_artifact(content_sha256=digest)
            if dup_artifact and str(dup_artifact.get("local_original_path") or "") != source.get("local_original_path", ""):
                source["status"] = "duplicate"
                source["is_duplicate"] = 1
                source["duplicate_of_source_id"] = str(dup_artifact.get("source_id") or "")
                source["local_original_path"] = str(dup_artifact.get("local_original_path") or source.get("local_original_path") or "")
                source["local_text_path"] = str(dup_artifact.get("local_text_path") or source.get("local_text_path") or "")
                source["local_markdown_path"] = str(dup_artifact.get("local_markdown_path") or source.get("local_markdown_path") or "")
            else:
                upsert_source_artifact(
                    source_id=str(source.get("source_id") or ""),
                    canonical_url=canonical_url,
                    final_url=str(download_result.get("final_url") or url),
                    content_sha256=digest,
                    content_type=str(download_result.get("content_type") or ""),
                    local_original_path=str(source.get("local_original_path") or ""),
                    local_text_path=str(source.get("local_text_path") or ""),
                    local_markdown_path=str(source.get("local_markdown_path") or ""),
                )
            saved_status = str(saved.get("status") or "downloaded")
            if source.get("status") not in {"duplicate"}:
                source["status"] = "degraded" if saved_status == "degraded" else "downloaded"
            return source
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            source["error"] = message
            if "timeout" in message.lower():
                source["status"] = "degraded"
                source["error"] = "download failed: timeout"
            elif "content too large" in message.lower():
                source["status"] = "skipped_size_limit"
            elif continue_on_download_error:
                source["status"] = "degraded"
            else:
                source["status"] = "failed"
                raise
            return source
        finally:
            source["finished_at"] = _now_iso()
            source["elapsed_sec"] = round(max(0.0, time.monotonic() - started), 3)

    futures: dict[Future, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, concurrency), thread_name_prefix="nexus-dl") as executor:
        for source in sources:
            if str(source.get("status")) == "skipped_download_limit":
                continue
            with lock:
                stats["active"] += 1
            futures[executor.submit(_worker, source)] = source

        while futures:
            done, _pending = wait(tuple(futures.keys()), timeout=max(1, download_progress_interval_sec), return_when=FIRST_COMPLETED)
            if not done:
                _emit_progress()
                continue

            for fut in done:
                source = futures.pop(fut)
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        stats["active"] = max(0, stats["active"] - 1)
                        stats["completed"] += 1
                        stats["failed"] += 1
                    source["status"] = "failed"
                    source["error"] = str(exc)
                    source["finished_at"] = source.get("finished_at") or _now_iso()
                    source["elapsed_sec"] = float(source.get("elapsed_sec") or 0.0)
                    append_job_event(
                        job_id,
                        "download_source_failed",
                        {
                            "status": "running",
                            "phase": "downloading",
                            "source_id": source.get("source_id"),
                            "url": source.get("url"),
                            "error": source.get("error"),
                            "updated_at": _now_iso(),
                        },
                    )
                    fatal_errors.append(exc)
                    continue

                status = str(result.get("status") or "")
                with lock:
                    stats["active"] = max(0, stats["active"] - 1)
                    stats["completed"] += 1
                    if status == "downloaded":
                        stats["downloaded"] += 1
                    elif status == "degraded":
                        stats["degraded"] += 1
                        download_error_count += 1
                    elif status == "failed":
                        stats["failed"] += 1
                        download_error_count += 1
                    elif status in {"skipped_download_limit", "skipped_size_limit"}:
                        stats["skipped"] += 1
                    else:
                        stats["degraded"] += 1
                        download_error_count += 1
                    last_completion_at = time.monotonic()

                event_name = "download_source_finished" if status in {"downloaded", "degraded", "skipped_download_limit", "skipped_size_limit"} else "download_source_failed"
                append_job_event(
                    job_id,
                    event_name,
                    {
                        "status": "running",
                        "phase": "downloading",
                        "source_id": result.get("source_id"),
                        "url": result.get("url"),
                        "title": result.get("title"),
                        "domain": result.get("domain"),
                        "source_status": status,
                        "error": result.get("error"),
                        "elapsed_sec": result.get("elapsed_sec"),
                        "size": result.get("size"),
                        "updated_at": result.get("finished_at") or _now_iso(),
                    },
                )
            _emit_progress()

    _emit_progress(force=True)
    append_job_event(
        job_id,
        "download_finished",
        {
            **_download_progress_payload(stats=stats, now_iso=_now_iso(), status="running"),
            "message": "download finished",
        },
    )
    if fatal_errors and not continue_on_download_error:
        raise ValueError(f"download failed and continue_on_download_error=false: {fatal_errors[0]}")
    return sources, download_error_count



def _run_news_profile_research(payload: ResearchAgentInput, *, effective_job_id: str, query: str) -> dict:
    """Run Deep Research with source_profile=news using the shared News Source layer."""

    budget = payload.news_budget or {}
    max_total_items = int(budget.get("max_total_items") or payload.max_sources or 15)
    max_providers = int(budget.get("max_providers") or 3)
    profile = NewsResearchSourceProfile(
        source_profile="news",
        mode=payload.mode if payload.mode in {"quick", "standard", "deep", "exhaustive"} else "standard",
        max_queries=payload.max_queries or 2,
        max_items=max(1, min(max_total_items, 50)),
        save_evidence=True,
        include_personal_use_only=False,
    )
    profile.providers = profile.providers[: max(1, min(max_providers, len(profile.providers)))]
    _emit_phase(effective_job_id, "news_search_started", phase="web_search", message="news source search started", progress=0.22)
    collected = collect_news_research_sources(query, profile=profile)
    evidence_items = convert_news_items_to_evidence(collected["items"], topic=query, job_kind="deep_research_news")
    save_evidence_items(effective_job_id, evidence_items, project=payload.project)
    references = [
        {
            "source_id": item.source_id,
            "citation_label": item.citation_label,
            "title": item.title,
            "url": item.url,
            "publisher": item.publisher,
            "source_type": item.source_type,
        }
        for item in evidence_items
    ]
    evidence_json = [
        {
            "source_id": item.source_id,
            "source_type": item.source_type,
            "url": item.url,
            "title": item.title,
            "publisher": item.publisher,
            "snippet": item.quote,
            "metadata_json": item.metadata_json,
        }
        for item in evidence_items
    ]
    source_chunks = [
        {
            "source_id": item.source_id,
            "chunk_id": item.chunk_id,
            "citation_label": item.citation_label,
            "title": item.title,
            "quote": item.quote or item.title,
        }
        for item in evidence_items
    ]
    summary = f"{query} に関するNews Deep Research結果です。News source profileで収集した根拠: " + " ".join(
        ref["citation_label"] for ref in references[:5]
    )
    answer_payload = build_answer_payload(
        question=query,
        summary=summary,
        references=references,
        evidence=evidence_json,
        evidence_chunks=source_chunks,
        job_id=effective_job_id,
        project=payload.project,
    )
    _emit_phase(effective_job_id, "news_search_finished", phase="web_search", message="news source search finished", progress=0.82, details={"result_count": len(evidence_items)})
    update_job(effective_job_id, status="completed", progress=1.0, message="news research completed")
    append_job_event(
        effective_job_id,
        "research_completed",
        {
            "status": "completed",
            "phase": "completed",
            "message": "news research completed",
            "progress": 1.0,
            "source_profile": "news",
            "source_count": len(evidence_items),
            "evidence_count": len(evidence_items),
            "updated_at": _now_iso(),
        },
    )
    return {
        "job_id": effective_job_id,
        "queries": collected.get("queries", []),
        "search": {
            **(collected.get("search", {}) or {}),
            "request_path": "/nexus/research/run",
            "source_profile": "news",
            "execution_path": "news_source_layer_rss_gdelt",
            "effective_engines": [],
            "effective_engines_news": [],
            "effective_news_providers": list(profile.providers),
        },
        "sources": evidence_json,
        "answer": answer_payload,
    }


def _init_replenishment_metrics(enabled: bool, engine_health_tracker: EngineHealthTracker | None = None) -> dict[str, Any]:
    health = engine_health_tracker.summary() if engine_health_tracker else {}
    return {
        "enabled": bool(enabled),
        "attempted": False,
        "replacement_queries": 0,
        "replacement_candidates": 0,
        "replacement_downloads": 0,
        "replacement_valid_sources": 0,
        "suspended_engines": list(health.get("suspended_engines") or []),
        "fallback_to_safe_engines": bool(health.get("fallback_to_safe_engines", False)),
        "replenishment_rounds": [],
        "failed_candidate_count": 0,
        "replacement_needed": False,
        "source_mix_deficits": {},
        "max_replenishment_downloads": 0,
        "replenishment_download_attempts_used": 0,
        "replenishment_download_budget_remaining": 0,
        "stop_reason": "not_attempted" if enabled else "disabled",
    }


def _select_replenishment_candidates(ranked_candidates: list[dict], attempted: set[str], needed: int, deficits: dict) -> list[dict]:
    return _select_download_candidates(ranked_candidates, attempted, needed, {}, deficits)

def run_research_job(payload: ResearchAgentInput, *, job_id: str | None = None) -> dict:
    query = payload.query.strip()
    if not query:
        raise ValueError("query must not be empty")

    runtime_cfg = load_runtime_config()
    effective_job_id = job_id or f"research_{uuid.uuid4().hex}"
    queries: list[dict] = []
    search: dict = {}
    registered_sources: list[dict] = []
    downloadable_sources: list[dict] = []
    answer_payload: dict = {}
    download_error_count = 0
    max_sources = payload.max_sources if payload.max_sources is not None else 50
    max_downloads = payload.max_downloads if payload.max_downloads is not None else runtime_cfg.max_downloads
    requested_max_download_mb = payload.max_download_mb if payload.max_download_mb is not None else runtime_cfg.max_download_mb
    max_download_mb = min(500, max(1, requested_max_download_mb))
    max_download_bytes = max_download_mb * 1024 * 1024
    max_total_download_mb = (
        payload.max_total_download_mb
        if payload.max_total_download_mb is not None
        else runtime_cfg.max_total_download_mb
    )
    max_total_download_bytes = max_total_download_mb * 1024 * 1024
    download_timeout_sec = (
        payload.download_timeout_sec if payload.download_timeout_sec is not None else runtime_cfg.download_timeout_sec
    )
    if not job_id:
        create_job(
            effective_job_id,
            title=query,
            message="research queued",
            status="queued",
            metadata={
                "project": payload.project,
                "query": query,
                "search_type": payload.mode,
                "depth": payload.depth or payload.mode,
                "source_profile": payload.source_profile,
                "created_by": "nexus_research",
                "is_research_job": True,
            },
        )
    else:
        ensure_job_exists(effective_job_id, title=query, message="research queued", status="queued")

    normalized_source_profile = str(getattr(payload, "source_profile", "web") or "web").strip().lower()
    if normalized_source_profile == "news":
        return _run_news_profile_research(payload, effective_job_id=effective_job_id, query=query)

    try:
        _emit_phase(effective_job_id, "planning_started", phase="planning", message="planning started", progress=0.05)
        _record_state(effective_job_id, "planning", message="query planning", progress=0.1)
        depth_key = str(payload.depth or payload.mode or "standard").strip().lower()
        intent = infer_research_intent(query, payload.source_profile, depth_key)
        screening_settings = get_screening_settings(depth_key)
        screening_result: dict[str, Any] = {"candidates": [], "summary": {}, "payload": {}}
        if screening_settings.get("enabled"):
            append_job_event(effective_job_id, "screening_started", {"status": "running", "phase": "broad_screening", **screening_settings, "updated_at": _now_iso()})
            screening_result = run_broad_screening(
                intent,
                target_screening_candidates=int(screening_settings.get("target_screening_candidates") or 0),
                max_screening_queries=int(screening_settings.get("max_screening_queries") or 1),
                max_results_per_query=int(screening_settings.get("max_results_per_query") or 10),
            )
            append_job_event(effective_job_id, "screening_completed", {"status": "running", "phase": "broad_screening", **dict(screening_result.get("payload") or {}), "updated_at": _now_iso()})
        screening_summary = dict(screening_result.get("summary") or {})
        focused_research_plan = build_focused_research_plan(intent, screening_summary, depth=depth_key)
        focused_queries = [str(item.get("query") or "").strip() for item in focused_research_plan.get("focused_queries") or [] if str(item.get("query") or "").strip()]
        queries = focused_queries or plan_web_queries(
            query,
            mode=payload.mode,
            depth=payload.depth,
            max_queries=payload.max_queries,
            scope=payload.scope,
            language=payload.language,
            source_profile=payload.source_profile,
        )
        _emit_phase(
            effective_job_id,
            "planning_finished",
            phase="planning",
            message="planning finished",
            progress=0.2,
            details={"queries": len(queries), "screening_candidates": int((screening_result.get("payload") or {}).get("unique_candidate_count") or 0), "focused_queries": len(focused_queries)},
        )
        update_job(effective_job_id, status="running", progress=0.2, message="searching web")

        targets = build_retrieval_targets(payload)
        if depth_key == "deep" and payload.max_downloads is None:
            max_downloads = max(max_downloads, 60)
        if depth_key == "exhaustive" and payload.max_downloads is None:
            max_downloads = max(max_downloads, 90)
        adaptive_enabled = bool(targets.get("adaptive_retrieval_enabled", True))
        max_rounds = int(targets.get("max_retrieval_rounds") or 1) if adaptive_enabled else 1
        max_rounds = max(1, min(max_rounds, 8))
        base_queries = list(queries)
        query_purpose_by_query = {str(item.get("query") or "").strip(): str(item.get("purpose") or "") for item in focused_research_plan.get("focused_queries") or []}
        all_items: list[dict] = []
        candidate_by_url: dict[str, dict] = {}
        attempted_canonical_urls: set[str] = set()
        retrieval_rounds: list[dict] = []
        static_curated_direct_candidates = build_curated_direct_source_candidates(query, payload.source_profile, intent)
        dynamic_screening_registry = extract_dynamic_topic_anchors_from_screening(query, list(screening_result.get("candidates") or []), intent)
        dynamic_curated_direct_candidates = build_dynamic_direct_source_candidates(
            query,
            payload.source_profile,
            screening_candidates=list(screening_result.get("candidates") or []),
            intent=intent,
            screening_summary=screening_summary,
        )
        curated_direct_candidates: list[dict] = []
        seen_direct: set[str] = set()
        for direct_candidate in [*static_curated_direct_candidates, *dynamic_curated_direct_candidates]:
            canonical_direct = canonicalize_source_url(str(direct_candidate.get("url") or "")) or str(direct_candidate.get("url") or "")
            if canonical_direct and canonical_direct not in seen_direct:
                seen_direct.add(canonical_direct)
                curated_direct_candidates.append(direct_candidate)
        static_curated_direct_count = len(static_curated_direct_candidates)
        dynamic_curated_direct_count = sum(1 for item in curated_direct_candidates if str(item.get("origin") or "") == "dynamic_curated_direct_source")
        dynamic_curated_direct_domains = sorted({urlparse(str(item.get("url") or "")).netloc.lower() for item in curated_direct_candidates if str(item.get("origin") or "") == "dynamic_curated_direct_source" and str(item.get("url") or "")})
        curated_direct_domains = sorted({urlparse(str(item.get("url") or "")).netloc.lower() for item in curated_direct_candidates if str(item.get("url") or "")})
        engine_health_tracker = EngineHealthTracker()
        skipped_due_to_download_limit_count = 0
        last_expand_reasons: list[str] = []
        cumulative_downloaded_bytes = 0
        replenishment_metrics = _init_replenishment_metrics(bool(targets.get("replenishment_enabled", True)), engine_health_tracker)

        _emit_phase(effective_job_id, "web_search_started", phase="web_search", message="web search started", progress=0.22)
        _record_state(effective_job_id, "searching", message="running web search", progress=0.25)

        for round_index in range(max_rounds):
            strategy = build_retrieval_strategy(payload.source_profile, str(payload.depth or payload.mode or "standard"), round_index, {"reasons": last_expand_reasons})
            if focused_queries and round_index == 0:
                round_queries = focused_queries[: max(1, payload.max_queries or len(focused_queries))]
            else:
                round_queries = _retrieval_strategy_queries(base_queries, strategy, query, payload.source_profile, max(1, payload.max_queries or len(base_queries) or 1) + (round_index * 6))
            append_job_event(
                effective_job_id,
                "retrieval_round_started",
                {
                    "round": round_index + 1,
                    "strategy": strategy.get("name"),
                    "query_count": len(round_queries),
                    "expand_reasons": last_expand_reasons,
                    "status": "running",
                    "phase": "web_search",
                    "updated_at": _now_iso(),
                },
            )
            round_search = run_web_search(
                round_queries,
                mode=payload.mode,
                depth=payload.depth,
                max_results_per_query=payload.max_results_per_query,
                scope=payload.scope,
                language=payload.language,
                source_profile=payload.source_profile,
                freshness="recent" if str(payload.source_profile or "").lower() in {"news", "market"} else "balanced",
                engine_health_tracker=engine_health_tracker,
            )
            if round_index == 0:
                search = round_search
            else:
                search.setdefault("retrieval_round_searches", []).append(round_search)
            round_items = list(round_search.get("items") or [])
            for _item in round_items:
                _item["query_purpose"] = query_purpose_by_query.get(str(_item.get("query") or "").strip(), "")
            all_items.extend(round_items)
            round_candidates = collect_source_candidates(
                search_items=all_items,
                manual_urls=payload.manual_urls if round_index == 0 else [],
                direct_source_candidates=curated_direct_candidates if round_index == 0 else [],
            )
            ranked_all = rank_source_candidates(
                round_candidates,
                prefer_pdf=payload.prefer_pdf,
                official_first=payload.official_first,
                query=query,
                trusted_domain_hints=get_curated_domain_hints(query, payload.source_profile),
                source_profile=payload.source_profile,
            )
            ranked_all, stub_filtered_count = _filter_stub_candidates(ranked_all, payload)
            if stub_filtered_count:
                append_job_event(
                    effective_job_id,
                    "stub_sources_filtered",
                    {
                        "status": "running",
                        "phase": "source_collection",
                        "message": "stub search results filtered from deep research evidence",
                        "filtered_count": stub_filtered_count,
                        "updated_at": _now_iso(),
                    },
                )
            for candidate in ranked_all:
                canonical = canonicalize_source_url(str(candidate.get("url") or "")) or str(candidate.get("url") or "")
                if canonical and canonical not in candidate_by_url:
                    candidate_by_url[canonical] = candidate
            ranked_candidates = list(candidate_by_url.values())
            ranked_candidates = rank_source_candidates(
                ranked_candidates,
                prefer_pdf=payload.prefer_pdf,
                official_first=payload.official_first,
                query=query,
                trusted_domain_hints=get_curated_domain_hints(query, payload.source_profile),
                source_profile=payload.source_profile,
            )[:max_sources]

            if stub_filtered_count and not ranked_candidates and round_index == max_rounds - 1:
                message = "Web検索 provider が有効な実ソースを返せなかったため、根拠付き回答は生成できません"
                answer_payload = {
                    "question": query,
                    "answer": message,
                    "summary": message,
                    "answer_markdown": message,
                    "references": [],
                    "evidence": [],
                    "output_incomplete": True,
                    "generation_mode": "stub_filtered_no_real_sources",
                    "stub_sources_filtered": stub_filtered_count,
                }
                answer_payload["claim_analysis"] = analyze_claim_level_gaps(answer_payload, [], [])
                save_minimal_research_answer(job_id=effective_job_id, project=payload.project, question=query, answer_payload=answer_payload)
                update_job(effective_job_id, status="failed", progress=1.0, message="検索結果を取得できませんでした。検索エンジン設定、SearXNG疎通、またはクエリを確認してください。")
                no_sources_payload = {"status": "failed", "phase": "no_sources", "message": "検索結果を取得できませんでした。検索エンジン設定、SearXNG疎通、またはクエリを確認してください。", "reason": "no_sources", "filtered_count": stub_filtered_count, "source_count": 0, "evidence_count": 0, "updated_at": _now_iso()}
                append_job_event(effective_job_id, "research_completed", no_sources_payload)
                append_job_event(effective_job_id, "research_failed", no_sources_payload)
                return {"job_id": effective_job_id, "queries": queries, "search": search, "sources": [], "answer": answer_payload}

            remaining_downloads = max(0, max_downloads - len(attempted_canonical_urls))
            to_download: list[dict] = []
            if remaining_downloads > 0:
                to_download = _select_download_candidates(ranked_candidates, attempted_canonical_urls, remaining_downloads, focused_research_plan.get("source_mix_targets"))
                for candidate in to_download:
                    canonical = canonicalize_source_url(str(candidate.get("url") or "")) or str(candidate.get("url") or "")
                    if canonical:
                        attempted_canonical_urls.add(canonical)
            skipped_due_to_download_limit_count = max(0, len(ranked_candidates) - len(attempted_canonical_urls))

            if to_download:
                if round_index == 0:
                    _emit_phase(effective_job_id, "download_phase_started", phase="downloading", message="download phase started", progress=0.55, details={"total_candidates": len(ranked_candidates), "max_downloads": max_downloads})
                remaining_total_bytes = max(0, max_total_download_bytes - cumulative_downloaded_bytes)
                round_downloaded, round_download_errors = _download_sources_parallel(
                    job_id=effective_job_id,
                    candidates=to_download,
                    max_downloads=len(to_download),
                    max_download_bytes=max_download_bytes,
                    max_total_download_bytes=remaining_total_bytes,
                    download_timeout_sec=download_timeout_sec,
                    continue_on_download_error=payload.continue_on_download_error,
                    concurrency=runtime_cfg.download_concurrency,
                    pdf_extract_concurrency=runtime_cfg.pdf_extract_concurrency,
                    download_progress_interval_sec=runtime_cfg.download_progress_interval_sec,
                    download_stalled_after_sec=runtime_cfg.download_stalled_after_sec,
                )
                downloadable_sources.extend(round_downloaded)
                download_error_count += round_download_errors
                cumulative_downloaded_bytes += sum(max(0, int(item.get("size") or 0)) for item in round_downloaded if str(item.get("status") or "") in {"downloaded", "degraded", "reused"})
                round_registered = register_or_update_sources(job_id=effective_job_id, project=payload.project, sources=round_downloaded)
                existing = {str(item.get("source_id") or ""): item for item in registered_sources if str(item.get("source_id") or "")}
                for item in round_registered:
                    sid = str(item.get("source_id") or "")
                    if sid:
                        existing[sid] = item
                registered_sources = list(existing.values())

            source_chunks = _load_source_chunks([str(item.get("source_id") or "") for item in registered_sources])
            current_summary = _retrieval_summary(
                targets=targets,
                retrieval_rounds=retrieval_rounds,
                candidate_count=len(ranked_candidates),
                attempted_download_count=len(attempted_canonical_urls),
                registered_sources=registered_sources,
                evidence_chunks=source_chunks,
                skipped_due_to_download_limit_count=skipped_due_to_download_limit_count,
                intent=intent,
                screening_summary=screening_summary,
                focused_research_plan=focused_research_plan,
                search_policy=resolve_searxng_engines_for_profile(payload.source_profile, str(payload.depth or payload.mode or "standard"), "recent" if str(payload.source_profile or "").lower() in {"news", "market"} else "balanced"),
                curated_direct_candidate_count=len(curated_direct_candidates),
                static_curated_direct_candidate_count=static_curated_direct_count,
                dynamic_curated_direct_candidate_count=dynamic_curated_direct_count,
                curated_direct_downloaded_count=sum(1 for item in downloadable_sources if str(item.get("origin") or "") in {"curated_direct_source", "dynamic_curated_direct_source"} and str(item.get("status") or "") in {"downloaded", "degraded", "reused", "ingested"}),
                curated_direct_domains=curated_direct_domains,
                dynamic_curated_direct_domains=dynamic_curated_direct_domains,
                dynamic_screening_registry=dynamic_screening_registry,
                engine_health=engine_health_tracker.summary(),
                engine_replenishment=replenishment_metrics,
            )
            expand, reasons = should_expand_retrieval(current_summary, targets, round_index + 1)
            round_payload = {
                "round": round_index + 1,
                "strategy": strategy.get("name"),
                "query_count": len(round_queries),
                "candidate_count": len(ranked_candidates),
                "new_candidate_count": len(to_download),
                "attempted_download_count": len(attempted_canonical_urls),
                "valid_source_count": current_summary.get("valid_source_count", 0),
                "evidence_count": current_summary.get("evidence_count", 0),
                "high_quality_source_count": current_summary.get("high_quality_source_count", 0),
                "official_source_count": current_summary.get("official_source_count", 0),
                "pdf_source_count": current_summary.get("pdf_source_count", 0),
                "skipped_due_to_download_limit_count": skipped_due_to_download_limit_count,
                "expand_reasons": reasons,
                "status": "running",
                "phase": "web_search",
                "updated_at": _now_iso(),
            }
            retrieval_rounds.append(round_payload)
            append_job_event(effective_job_id, "retrieval_round_completed", round_payload)
            last_expand_reasons = reasons
            if not adaptive_enabled or not expand:
                break

        if bool(targets.get("replenishment_enabled", True)):
            max_replenishment_rounds = max(0, int(targets.get("max_replenishment_rounds") or 0))
            max_replenishment_candidates = max(0, int(targets.get("max_replenishment_candidates") or 0))
            max_replenishment_downloads = max(0, int(targets.get("max_replenishment_downloads") or 0))
            replacement_candidate_budget_used = 0
            replenishment_download_attempts_used = 0
            replenishment_metrics["max_replenishment_downloads"] = max_replenishment_downloads
            replenishment_metrics["replenishment_download_attempts_used"] = replenishment_download_attempts_used
            replenishment_metrics["replenishment_download_budget_remaining"] = max(0, max_replenishment_downloads - replenishment_download_attempts_used)
            for replenishment_round_index in range(max_replenishment_rounds):
                source_chunks = _load_source_chunks([str(item.get("source_id") or "") for item in registered_sources])
                failed_sources = _collect_failed_retrieval_items(ranked_candidates, downloadable_sources)
                current_summary = _retrieval_summary(
                    targets=targets,
                    retrieval_rounds=retrieval_rounds,
                    candidate_count=len(ranked_candidates),
                    attempted_download_count=len(attempted_canonical_urls),
                    registered_sources=registered_sources,
                    evidence_chunks=source_chunks,
                    skipped_due_to_download_limit_count=skipped_due_to_download_limit_count,
                    intent=intent,
                    screening_summary=screening_summary,
                    focused_research_plan=focused_research_plan,
                    search_policy=resolve_searxng_engines_for_profile(payload.source_profile, str(payload.depth or payload.mode or "standard"), "recent" if str(payload.source_profile or "").lower() in {"news", "market"} else "balanced"),
                    engine_health=engine_health_tracker.summary(),
                    engine_replenishment=replenishment_metrics,
                )
                current_summary["failed_sources"] = failed_sources
                deficit = compute_retrieval_deficit(current_summary, targets)
                replenishment_metrics["failed_candidate_count"] = deficit.get("failed_candidate_count", 0)
                replenishment_metrics["replacement_needed"] = deficit.get("replacement_needed", False)
                replenishment_metrics["source_mix_deficits"] = deficit.get("source_mix_deficits", {})
                if not deficit.get("replacement_needed"):
                    replenishment_metrics["stop_reason"] = "targets_satisfied"
                    break
                remaining_replacement_budget = max(0, max_replenishment_candidates - replacement_candidate_budget_used)
                if remaining_replacement_budget <= 0:
                    replenishment_metrics["stop_reason"] = "candidate_budget_exhausted"
                    break
                remaining_replenishment_downloads = max(0, max_replenishment_downloads - replenishment_download_attempts_used)
                needed = min(int(deficit.get("replacement_target_count") or 0), remaining_replacement_budget, remaining_replenishment_downloads)
                if needed <= 0:
                    replenishment_metrics["stop_reason"] = "download_budget_exhausted"
                    break
                suspended = list(engine_health_tracker.summary().get("suspended_engines") or [])
                replacement_query_objs = build_replenishment_queries(query, intent, focused_research_plan, deficit, failed_sources, suspended)
                if not replacement_query_objs:
                    replenishment_metrics["stop_reason"] = "no_replacement_queries"
                    break
                replacement_queries = [str(item.get("query") or "").strip() for item in replacement_query_objs if str(item.get("query") or "").strip()]
                preferred_engines: list[str] = []
                for item in replacement_query_objs:
                    for engine in item.get("preferred_engines") or []:
                        if str(engine).lower() not in [e.lower() for e in preferred_engines]:
                            preferred_engines.append(str(engine))
                if not preferred_engines:
                    preferred_engines = choose_replacement_engines(payload.source_profile, None, set(suspended))
                append_job_event(effective_job_id, "replenishment_round_started", {"round": replenishment_round_index + 1, "status": "running", "phase": "web_search", "message": "不足分を追加検索中", "replacement_target_count": needed, "updated_at": _now_iso()})
                _emit_phase(effective_job_id, "replenishment_search_started", phase="web_search", message="不足分を追加検索中", progress=0.33, details={"round": replenishment_round_index + 1, "needed": needed})
                replacement_search = run_web_search(
                    replacement_queries,
                    mode=payload.mode,
                    depth=payload.depth,
                    max_results_per_query=payload.max_results_per_query,
                    scope=payload.scope,
                    language=payload.language,
                    source_profile=payload.source_profile,
                    freshness="recent" if str(payload.source_profile or "").lower() in {"news", "market"} else "balanced",
                    engine_health_tracker=engine_health_tracker,
                )
                replacement_items = list(replacement_search.get("items") or [])
                for item in replacement_items:
                    item["query_purpose"] = "replenish_failed_sources"
                dynamic_direct = build_dynamic_direct_source_candidates(query, payload.source_profile, list(screening_result.get("candidates") or []), intent=intent, screening_summary=screening_summary)
                replacement_candidates = collect_source_candidates(search_items=replacement_items, manual_urls=[], direct_source_candidates=dynamic_direct)
                for candidate in replacement_candidates:
                    canonical = canonicalize_source_url(str(candidate.get("url") or "")) or str(candidate.get("url") or "")
                    if canonical and canonical not in candidate_by_url:
                        candidate_by_url[canonical] = candidate
                ranked_candidates = rank_source_candidates(list(candidate_by_url.values()), prefer_pdf=payload.prefer_pdf, official_first=payload.official_first, query=query, trusted_domain_hints=get_curated_domain_hints(query, payload.source_profile), source_profile=payload.source_profile)[:max_sources]
                selected = _select_replenishment_candidates(ranked_candidates, attempted_canonical_urls, needed, deficit)
                if not selected:
                    replenishment_metrics["stop_reason"] = "no_new_candidates"
                    break
                for candidate in selected:
                    canonical = canonicalize_source_url(str(candidate.get("url") or "")) or str(candidate.get("url") or "")
                    if canonical:
                        attempted_canonical_urls.add(canonical)
                replenishment_download_attempts_used += len(selected)
                remaining_total_bytes = max(0, max_total_download_bytes - cumulative_downloaded_bytes)
                downloaded_before = len(downloadable_sources)
                valid_before = sum(1 for item in registered_sources if str(item.get("status") or "") in {"downloaded", "degraded", "reused", "ingested", ""})
                round_downloaded, round_download_errors = _download_sources_parallel(
                    job_id=effective_job_id,
                    candidates=selected,
                    max_downloads=len(selected),
                    max_download_bytes=max_download_bytes,
                    max_total_download_bytes=remaining_total_bytes,
                    download_timeout_sec=download_timeout_sec,
                    continue_on_download_error=payload.continue_on_download_error,
                    concurrency=runtime_cfg.download_concurrency,
                    pdf_extract_concurrency=runtime_cfg.pdf_extract_concurrency,
                    download_progress_interval_sec=runtime_cfg.download_progress_interval_sec,
                    download_stalled_after_sec=runtime_cfg.download_stalled_after_sec,
                )
                downloadable_sources.extend(round_downloaded)
                download_error_count += round_download_errors
                cumulative_downloaded_bytes += sum(max(0, int(item.get("size") or 0)) for item in round_downloaded if str(item.get("status") or "") in {"downloaded", "degraded", "reused"})
                round_registered = register_or_update_sources(job_id=effective_job_id, project=payload.project, sources=round_downloaded)
                existing = {str(item.get("source_id") or ""): item for item in registered_sources if str(item.get("source_id") or "")}
                for item in round_registered:
                    sid = str(item.get("source_id") or "")
                    if sid:
                        existing[sid] = item
                registered_sources = list(existing.values())
                valid_after = sum(1 for item in registered_sources if str(item.get("status") or "") in {"downloaded", "degraded", "reused", "ingested", ""})
                replacement_candidate_budget_used += len(selected)
                replenishment_metrics["attempted"] = True
                replenishment_metrics["replacement_queries"] += len(replacement_queries)
                replenishment_metrics["replacement_candidates"] += len(selected)
                replenishment_metrics["replacement_downloads"] += max(0, len(downloadable_sources) - downloaded_before)
                replenishment_metrics["replacement_valid_sources"] += max(0, valid_after - valid_before)
                replenishment_metrics["replenishment_download_attempts_used"] = replenishment_download_attempts_used
                replenishment_metrics["replenishment_download_budget_remaining"] = max(0, max_replenishment_downloads - replenishment_download_attempts_used)
                health = engine_health_tracker.summary()
                replenishment_metrics["suspended_engines"] = list(health.get("suspended_engines") or [])
                replenishment_metrics["fallback_to_safe_engines"] = bool(health.get("fallback_to_safe_engines", False))
                round_payload = {"round": replenishment_round_index + 1, "status": "running", "phase": "web_search", "replacement_queries": len(replacement_queries), "replacement_candidates": len(replacement_candidates), "replacement_downloads": len(round_downloaded), "replacement_valid_sources": max(0, valid_after - valid_before), "deficit": deficit, "suspended_engines": replenishment_metrics["suspended_engines"], "updated_at": _now_iso()}
                replenishment_metrics["replenishment_rounds"].append(round_payload)
                append_job_event(effective_job_id, "replenishment_round_completed", {**round_payload, "message": f"補充: {len(round_downloaded)}件取得 / {max(0, valid_after - valid_before)}件有効"})
            else:
                if max_replenishment_rounds > 0:
                    replenishment_metrics["stop_reason"] = "max_replenishment_rounds_reached"

        ranked_candidates = list(candidate_by_url.values())[:max_sources]
        _emit_phase(effective_job_id, "web_search_finished", phase="web_search", message="web search finished", progress=0.35, details={"result_count": len(all_items), "retrieval_rounds": len(retrieval_rounds), "engine_replenishment": replenishment_metrics})
        _emit_phase(effective_job_id, "source_collection_started", phase="source_collection", message="source collection started", progress=0.36)
        _record_state(effective_job_id, "collecting_sources", message="normalizing source candidates", progress=0.4)
        if len(candidate_by_url) >= max_sources:
            append_job_event(effective_job_id, "constraint_applied", {"status": "running", "progress": 0.45, "message": f"candidate limit reached: max_sources={max_sources}", "reason": "max_sources_exceeded", "max_download_mb": max_download_mb, "max_download_bytes": max_download_bytes, "max_sources": max_sources, "candidate_count": len(candidate_by_url)})
        _emit_phase(effective_job_id, "source_collection_finished", phase="source_collection", message="source collection finished", progress=0.5, details={"candidate_count": len(ranked_candidates), "attempted_download_count": len(attempted_canonical_urls), "skipped_due_to_download_limit_count": skipped_due_to_download_limit_count})
        _emit_phase(effective_job_id, "download_phase_finished", phase="downloading", message="download phase finished", progress=0.65, details={"download_count": sum(1 for s in downloadable_sources if str(s.get("status")) in {"downloaded", "ingested", "reused", "degraded"}), "download_errors": download_error_count, "skipped_due_to_download_limit_count": skipped_due_to_download_limit_count})

        _emit_phase(effective_job_id, "source_ingest_started", phase="source_ingest", message="source ingest started", progress=0.66)
        evidence_items = _build_evidence_from_sources(effective_job_id, registered_sources)
        save_evidence_items(effective_job_id, evidence_items)
        _emit_phase(effective_job_id, "source_ingest_finished", phase="source_ingest", message="source ingest finished", progress=0.69, details={"source_count": len(registered_sources)})

        _emit_phase(effective_job_id, "evidence_retrieval_started", phase="evidence_retrieval", message="evidence retrieval started", progress=0.7)
        _record_state(effective_job_id, "retrieving_evidence", message="mapping citations", progress=0.7)
        source_chunks = _load_source_chunks([str(item.get("source_id") or "") for item in registered_sources])
        references = build_citation_map(registered_sources, source_chunks)
        normalized = normalize_reference_labels(
            references=references,
            evidence_json=registered_sources,
            evidence_chunks=source_chunks,
        )
        references = normalized["references"]
        registered_sources = normalized["evidence_json"]
        source_chunks = normalized["evidence_chunks"]
        _emit_phase(
            effective_job_id,
            "evidence_retrieval_finished",
            phase="evidence_retrieval",
            message="evidence retrieval finished",
            progress=0.77,
            details={"chunk_count": len(source_chunks)},
        )
        _emit_phase(
            effective_job_id,
            "evidence_compression_started",
            phase="evidence_compression",
            message="evidence compression started",
            progress=0.79,
        )
        _emit_phase(
            effective_job_id,
            "evidence_compression_finished",
            phase="evidence_compression",
            message="evidence compression finished",
            progress=0.82,
        )

        coverage_matrix = build_coverage_matrix(focused_research_plan, source_chunks, registered_sources)
        report_outline = build_report_outline(intent, focused_research_plan)
        _record_state(effective_job_id, "answering", message="building answer", progress=0.85)
        _emit_phase(
            effective_job_id,
            "answer_llm_request_started",
            phase="answer_llm_generating",
            message="answer llm request started",
            progress=0.84,
        )
        retrieval_summary = _retrieval_summary(
            targets=targets,
            retrieval_rounds=retrieval_rounds,
            candidate_count=len(ranked_candidates),
            attempted_download_count=len(attempted_canonical_urls),
            registered_sources=registered_sources,
            evidence_chunks=source_chunks,
            skipped_due_to_download_limit_count=skipped_due_to_download_limit_count,
            intent=intent,
            screening_summary=screening_summary,
            focused_research_plan=focused_research_plan,
            coverage_matrix=coverage_matrix,
            search_policy=resolve_searxng_engines_for_profile(payload.source_profile, str(payload.depth or payload.mode or "standard"), "recent" if str(payload.source_profile or "").lower() in {"news", "market"} else "balanced"),
            curated_direct_candidate_count=len(curated_direct_candidates),
            static_curated_direct_candidate_count=static_curated_direct_count,
            dynamic_curated_direct_candidate_count=dynamic_curated_direct_count,
            curated_direct_downloaded_count=sum(1 for item in downloadable_sources if str(item.get("origin") or "") in {"curated_direct_source", "dynamic_curated_direct_source"} and str(item.get("status") or "") in {"downloaded", "degraded", "reused", "ingested"}),
            curated_direct_domains=curated_direct_domains,
            dynamic_curated_direct_domains=dynamic_curated_direct_domains,
            dynamic_screening_registry=dynamic_screening_registry,
            engine_health=engine_health_tracker.summary(),
            engine_replenishment=replenishment_metrics,
        )
        if references:
            labels = [f"[S{i + 1}]" for i in range(len(references))]
            summary = f"{query} に関する調査結果です。確認済みソース: {' '.join(labels)}"
        else:
            summary = f"{query} に関する根拠は未確認です。現時点では断定できません。"
        answer_payload = build_answer_payload(
            question=query,
            summary=summary,
            references=references,
            evidence=registered_sources,
            evidence_chunks=source_chunks,
            job_id=effective_job_id,
            project=payload.project,
            retrieval_summary=retrieval_summary,
            report_outline=report_outline,
            coverage_matrix=coverage_matrix,
            source_mix_summary=retrieval_summary.get("source_mix", {}),
        )
        iterations: list[dict] = []
        final_confidence = 0.0
        unresolved_items: list[str] = []
        stop_reason = "recursive_disabled"
        cumulative_downloads = sum(
            1 for item in downloadable_sources if str(item.get("status") or "") in {"downloaded", "degraded", "reused"}
        )
        cumulative_downloaded_bytes = sum(
            max(0, int(item.get("size") or 0))
            for item in downloadable_sources
            if str(item.get("status") or "") in {"downloaded", "degraded", "reused"}
        )
        followup_search_count = 0
        followup_queries_count = 0
        added_sources_total = 0
        recursive_stop_reason = stop_reason
        if payload.recursive_search:
            recursive_stop_reason = "max_iterations_reached"
            completed_all_iterations = True
            for iteration in range(1, payload.max_iterations + 1):
                append_job_event(effective_job_id, "recursive_iteration_started", {"iteration": iteration, "status": "running", "updated_at": _now_iso()})
                append_job_event(effective_job_id, "recursive_gap_analysis_started", {"iteration": iteration, "status": "running", "updated_at": _now_iso()})
                analysis = _analyze_research_gaps(sources=registered_sources, evidence_chunks=source_chunks, answer_payload=answer_payload)
                append_job_event(
                    effective_job_id,
                    "recursive_gap_analysis_finished",
                    {"iteration": iteration, "status": "running", "analysis": analysis, "updated_at": _now_iso()},
                )
                try:
                    claim_summary = analysis.get("claim_analysis") or {}
                    append_job_event(
                        effective_job_id,
                        "claim_support_verified",
                        {
                            "iteration": iteration,
                            "claim_count": int(claim_summary.get("claim_count") or 0),
                            "supported_claim_count": int(claim_summary.get("supported_claim_count") or 0),
                            "weakly_supported_claim_count": int(claim_summary.get("weakly_supported_claim_count") or 0),
                            "unsupported_claim_count": int(claim_summary.get("unsupported_claim_count") or 0),
                            "unresolved_claim_count": int(claim_summary.get("unresolved_claim_count") or 0),
                            "average_support_score": float(claim_summary.get("average_support_score") or 0.0),
                            "average_source_quality_score": float(claim_summary.get("average_source_quality_score") or 0.0),
                            "high_quality_supported_claim_count": int(claim_summary.get("high_quality_supported_claim_count") or 0),
                            "low_quality_supported_claim_count": int(claim_summary.get("low_quality_supported_claim_count") or 0),
                            "contradiction_count": int(claim_summary.get("contradiction_count") or 0),
                            "gaps": list(claim_summary.get("gaps") or []),
                            "updated_at": _now_iso(),
                        },
                    )
                except Exception:
                    pass
                final_confidence = float(analysis.get("confidence") or 0.0)
                unresolved_items = list(analysis.get("unresolved_items") or [])
                should_stop, reason = _should_stop_recursive_research(analysis=analysis, iteration=iteration, payload=payload)
                if should_stop:
                    completed_all_iterations = False
                    recursive_stop_reason = reason
                    stop_reason = reason
                    iteration_payload = {"iteration": iteration, "analysis": analysis, "followup_queries": [], "followup_search_executed": False, "added_sources": 0, "stop_reason": reason}
                    iterations.append(iteration_payload)
                    append_job_event(effective_job_id, "recursive_stopped", {"iteration": iteration, "status": "running", "reason": reason, "updated_at": _now_iso()})
                    append_job_event(effective_job_id, "recursive_iteration_finished", {"iteration": iteration, "status": "running", "followup_search_executed": False, "updated_at": _now_iso()})
                    break
                followup_queries = _generate_followup_queries(
                    original_query=query,
                    gaps=list(analysis.get("gaps") or []),
                    max_followup_queries=payload.max_followup_queries,
                    claim_analysis=analysis.get("claim_analysis"),
                )
                followup_queries_count += len(followup_queries)
                append_job_event(effective_job_id, "recursive_followup_queries_generated", {"iteration": iteration, "queries": followup_queries, "status": "running", "updated_at": _now_iso()})
                if not followup_queries:
                    completed_all_iterations = False
                    recursive_stop_reason = "no_followup_queries"
                    stop_reason = "no_followup_queries"
                    append_job_event(effective_job_id, "recursive_stopped", {"iteration": iteration, "status": "running", "reason": stop_reason, "updated_at": _now_iso()})
                    iterations.append({"iteration": iteration, "analysis": analysis, "followup_queries": [], "followup_search_executed": False, "added_sources": 0, "stop_reason": stop_reason})
                    append_job_event(effective_job_id, "recursive_iteration_finished", {"iteration": iteration, "status": "running", "followup_search_executed": False, "updated_at": _now_iso()})
                    break
                remaining_downloads = max(0, max_downloads - cumulative_downloads)
                remaining_total_bytes = max(0, max_total_download_bytes - cumulative_downloaded_bytes)
                if remaining_downloads <= 0 or remaining_total_bytes <= 0:
                    completed_all_iterations = False
                    recursive_stop_reason = "download_budget_exhausted"
                    stop_reason = "download_budget_exhausted"
                    append_job_event(effective_job_id, "recursive_stopped", {"iteration": iteration, "status": "running", "reason": stop_reason, "updated_at": _now_iso()})
                    iterations.append({"iteration": iteration, "analysis": analysis, "followup_queries": followup_queries, "followup_search_executed": False, "added_sources": 0, "stop_reason": stop_reason})
                    append_job_event(effective_job_id, "recursive_iteration_finished", {"iteration": iteration, "status": "running", "followup_search_executed": False, "updated_at": _now_iso()})
                    break
                append_job_event(effective_job_id, "recursive_followup_search_started", {"iteration": iteration, "status": "running", "updated_at": _now_iso()})
                followup_search_count += 1
                followup_search = run_web_search(followup_queries, mode=payload.mode, depth=payload.depth, max_results_per_query=payload.max_results_per_query, scope=payload.scope, language=payload.language)
                followup_candidates = collect_source_candidates(search_items=list(followup_search.get("items") or []), manual_urls=[])
                followup_ranked = rank_source_candidates(followup_candidates, prefer_pdf=payload.prefer_pdf, official_first=payload.official_first)
                followup_ranked, followup_stub_filtered_count = _filter_stub_candidates(followup_ranked, payload)
                if followup_stub_filtered_count:
                    append_job_event(effective_job_id, "stub_sources_filtered", {"iteration": iteration, "status": "running", "filtered_count": followup_stub_filtered_count, "updated_at": _now_iso()})
                existing_canonicals = {
                    canonicalize_source_url(str(s.get("canonical_url") or s.get("final_url") or s.get("url") or ""))
                    for s in registered_sources
                    if str(s.get("canonical_url") or s.get("final_url") or s.get("url") or "").strip()
                }
                batch_canonicals: set[str] = set()
                filtered_followup_ranked: list[dict] = []
                for candidate in followup_ranked:
                    canonical = canonicalize_source_url(str(candidate.get("canonical_url") or candidate.get("url") or ""))
                    if not canonical:
                        continue
                    if canonical in existing_canonicals or canonical in batch_canonicals:
                        continue
                    batch_canonicals.add(canonical)
                    filtered_followup_ranked.append(candidate)
                if not filtered_followup_ranked:
                    completed_all_iterations = False
                    recursive_stop_reason = "no_new_sources"
                    stop_reason = "no_new_sources"
                    append_job_event(effective_job_id, "recursive_stopped", {"iteration": iteration, "status": "running", "reason": stop_reason, "updated_at": _now_iso()})
                    iterations.append({"iteration": iteration, "analysis": analysis, "followup_queries": followup_queries, "followup_search_executed": True, "added_sources": 0, "stop_reason": stop_reason})
                    append_job_event(effective_job_id, "recursive_iteration_finished", {"iteration": iteration, "status": "running", "followup_search_executed": True, "updated_at": _now_iso()})
                    break
                followup_downloaded, _ = _download_sources_parallel(
                    job_id=effective_job_id,
                    candidates=filtered_followup_ranked,
                    max_downloads=remaining_downloads,
                    max_download_bytes=max_download_bytes,
                    max_total_download_bytes=remaining_total_bytes,
                    download_timeout_sec=download_timeout_sec,
                    continue_on_download_error=payload.continue_on_download_error,
                    concurrency=runtime_cfg.download_concurrency,
                    pdf_extract_concurrency=runtime_cfg.pdf_extract_concurrency,
                    download_progress_interval_sec=runtime_cfg.download_progress_interval_sec,
                    download_stalled_after_sec=runtime_cfg.download_stalled_after_sec,
                )
                newly_downloaded = [
                    item for item in followup_downloaded if str(item.get("status") or "") in {"downloaded", "degraded", "reused"}
                ]
                cumulative_downloads += len(newly_downloaded)
                cumulative_downloaded_bytes += sum(max(0, int(item.get("size") or 0)) for item in newly_downloaded)
                followup_registered = register_or_update_sources(job_id=effective_job_id, project=payload.project, sources=followup_downloaded)
                if not followup_registered:
                    completed_all_iterations = False
                    recursive_stop_reason = "no_new_sources"
                    stop_reason = "no_new_sources"
                    append_job_event(effective_job_id, "recursive_stopped", {"iteration": iteration, "status": "running", "reason": stop_reason, "updated_at": _now_iso()})
                    iterations.append({"iteration": iteration, "analysis": analysis, "followup_queries": followup_queries, "followup_search_executed": True, "added_sources": 0, "stop_reason": stop_reason})
                    append_job_event(effective_job_id, "recursive_iteration_finished", {"iteration": iteration, "status": "running", "followup_search_executed": True, "updated_at": _now_iso()})
                    break
                source_index = {str(s.get("source_id") or ""): s for s in registered_sources}
                for source in followup_registered:
                    sid = str(source.get("source_id") or "")
                    if sid and sid not in source_index:
                        source_index[sid] = source
                registered_sources = list(source_index.values())
                source_chunks = _load_source_chunks([str(item.get("source_id") or "") for item in registered_sources])
                normalized = normalize_reference_labels(
                    references=build_citation_map(registered_sources, source_chunks),
                    evidence_json=registered_sources,
                    evidence_chunks=source_chunks,
                )
                references = normalized["references"]
                registered_sources = normalized["evidence_json"]
                source_chunks = normalized["evidence_chunks"]
                answer_payload = build_answer_payload(
                    question=query,
                    summary=summary,
                    references=references,
                    evidence=registered_sources,
                    evidence_chunks=source_chunks,
                    job_id=effective_job_id,
                    project=payload.project,
                    retrieval_summary=retrieval_summary,
                )
                added_count = len(followup_registered)
                added_sources_total += added_count
                append_job_event(effective_job_id, "recursive_followup_search_finished", {"iteration": iteration, "status": "running", "added_sources": added_count, "updated_at": _now_iso()})
                iterations.append({"iteration": iteration, "analysis": analysis, "followup_queries": followup_queries, "followup_search_executed": True, "added_sources": added_count, "stop_reason": ""})
                append_job_event(effective_job_id, "recursive_iteration_finished", {"iteration": iteration, "status": "running", "followup_search_executed": True, "updated_at": _now_iso()})
            if completed_all_iterations:
                stop_reason = "max_iterations_reached"
                append_job_event(
                    effective_job_id,
                    "recursive_stopped",
                    {
                        "iteration": payload.max_iterations,
                        "status": "running",
                        "reason": "max_iterations_reached",
                        "followup_search_count": followup_search_count,
                        "followup_queries_count": followup_queries_count,
                        "added_sources_total": added_sources_total,
                        "updated_at": _now_iso(),
                    },
                )
                if iterations and not str(iterations[-1].get("stop_reason") or "").strip():
                    iterations[-1]["stop_reason"] = "max_iterations_reached"
            final_evidence_items = _build_evidence_from_sources(effective_job_id, registered_sources)
            replace_evidence_items_for_job(effective_job_id, final_evidence_items, project=payload.project)
        else:
            analysis = _analyze_research_gaps(sources=registered_sources, evidence_chunks=source_chunks, answer_payload=answer_payload)
            final_confidence = float(analysis.get("confidence") or 0.0)
            unresolved_items = list(analysis.get("unresolved_items") or [])
            iterations = []
        if isinstance(analysis, dict) and analysis.get("claim_analysis") is not None:
            answer_payload["claim_analysis"] = analysis.get("claim_analysis")
        answer_payload["recursive_search"] = bool(payload.recursive_search)
        answer_payload["iterations"] = iterations
        answer_payload["confidence"] = final_confidence
        answer_payload["unresolved_items"] = unresolved_items
        answer_payload["stop_reason"] = stop_reason
        answer_payload["recursive_stop_reason"] = recursive_stop_reason
        answer_payload["followup_search_count"] = followup_search_count
        answer_payload["followup_queries_count"] = followup_queries_count
        answer_payload["added_sources_total"] = added_sources_total
        answer_payload["answer_generated"] = bool(str(answer_payload.get("answer_markdown") or answer_payload.get("answer") or "").strip())
        answer_payload["answer_saved"] = False
        answer_payload["citation_verification_done"] = bool(answer_payload.get("citation_verification"))
        answer_payload["gap_analysis_done"] = bool(answer_payload.get("claim_analysis") is not None or answer_payload.get("unresolved_items") is not None)
        answer_payload["bundle_saved"] = False
        answer_payload["finalization_warning"] = None
        _persist_latest_answer_json(effective_job_id, answer_payload)
        answer_payload["answer_saved"] = True
        _persist_latest_answer_json(effective_job_id, answer_payload)
        generation = answer_payload.get("generation") or {}
        generation_mode = (
            answer_payload.get("generation_mode")
            or generation.get("mode")
            or ""
        )
        llm_event_details = {
            "generation_mode": generation_mode,
            "finish_reason": generation.get("finish_reason"),
            "output_incomplete": generation.get("output_incomplete", answer_payload.get("output_incomplete")),
            "output_truncated": generation.get("output_truncated", answer_payload.get("output_truncated")),
            "error": generation.get("error", answer_payload.get("llm_error")),
            "elapsed_sec": generation.get("elapsed_sec"),
            "response_length_chars": generation.get("response_length_chars"),
        }
        if generation_mode in {"llm_answer", "llm_answer_truncated"} and not generation.get("error"):
            _emit_phase(
                effective_job_id,
                "answer_llm_request_finished",
                phase="answer_llm_generating",
                message="answer llm request finished",
                progress=0.9,
                details=llm_event_details,
            )
        else:
            failed_message = "answer llm request failed, fallback used"
            failed_event = "answer_llm_request_failed"
            if generation_mode in {"llm_answer_truncated", "llm_answer"}:
                failed_event = "answer_llm_request_degraded"
                failed_message = "answer llm request degraded"
            _emit_phase(
                effective_job_id,
                failed_event,
                phase="answer_llm_generating",
                message=failed_message,
                progress=0.9,
                details=llm_event_details,
            )
        _emit_phase(effective_job_id, "answer_validation_started", phase="answer_validation", message="answer validation started", progress=0.9)
        _emit_phase(effective_job_id, "answer_validation_finished", phase="answer_validation", message="answer validation finished", progress=0.92)
        _emit_phase(effective_job_id, "answer_save_started", phase="answer_save", message="answer save started", progress=0.93)
        _emit_phase(effective_job_id, "answer_save_finished", phase="answer_save", message="answer save finished", progress=0.94)

        _record_state(effective_job_id, "reporting", message="finalizing report", progress=0.95)
        reporting_started_at = time.time()
        source_has_degraded_or_failed = any(
            str(source.get("status") or "") in {"degraded", "failed"} for source in registered_sources
        )
        final_evidence = final_evidence_items if payload.recursive_search else evidence_items
        final_outcome = _determine_final_research_outcome(
            retrieval_summary=retrieval_summary,
            registered_sources=registered_sources,
            evidence_chunks=source_chunks,
            answer_payload=answer_payload,
            download_error_count=download_error_count,
            source_has_degraded_or_failed=source_has_degraded_or_failed,
        )
        reporting_max = EXHAUSTIVE_REPORTING_TIMEOUT_SEC if str(payload.depth or payload.mode or "").strip().lower() == "exhaustive" else REPORTING_TIMEOUT_SEC
        if bool(answer_payload.get("answer_generated")) and (time.time() - reporting_started_at) > reporting_max:
            final_outcome = {"status": "degraded", "reason": "reporting_timeout_after_answer_generated", "phase": "completed", "message": "research completed with reporting timeout after answer generation"}
            answer_payload["finalization_warning"] = "reporting_timeout_after_answer_generated"
        answer_payload["bundle_saved"] = True
        _persist_latest_answer_json(effective_job_id, answer_payload)
        update_job(effective_job_id, status=final_outcome["status"], progress=1.0, message=final_outcome["message"])
        completion_payload = {
            "status": final_outcome["status"],
            "phase": final_outcome["phase"],
            "reason": final_outcome["reason"],
            "message": final_outcome["message"],
            "progress": 1.0,
            "answer_exists": bool(answer_payload),
            "source_count": len(registered_sources),
            "evidence_count": len(final_evidence or []),
            "updated_at": _now_iso(),
        }
        append_job_event(
            effective_job_id,
            "research_completed",
            completion_payload,
        )
        if final_outcome["status"] == "failed":
            append_job_event(effective_job_id, "research_failed", completion_payload)
        elif final_outcome["status"] == "degraded":
            append_job_event(effective_job_id, "research_degraded", completion_payload)

        return {
            "job_id": effective_job_id,
            "queries": queries,
            "search": search,
            "sources": registered_sources,
            "answer": answer_payload,
        }
    except Exception as exc:  # noqa: BLE001
        all_sources_degraded = bool(downloadable_sources) and not any(
            str(source.get("status") or "") in {"downloaded", "ingested"} for source in downloadable_sources
        )
        if (
            payload.continue_on_download_error
            and download_error_count > 0
            and all_sources_degraded
            and _is_body_shortage_error(exc)
        ):
            update_job(
                effective_job_id,
                status="degraded",
                progress=1.0,
                message="research completed with degraded downloads",
                error=str(exc),
            )
            append_job_event(
                effective_job_id,
                "job_degraded",
                {
                    "status": "degraded",
                    "progress": 1.0,
                    "message": "research completed with degraded downloads",
                    "reason": "download_only_body_shortage",
                    "download_error_count": download_error_count,
                    "error": str(exc),
                },
            )
            _emit_phase(
                effective_job_id,
                "job_completed",
                phase="completed",
                message="job completed (degraded)",
                progress=1.0,
                status="degraded",
            )
            _record_state(effective_job_id, "completed", message="job completed (degraded)", progress=1.0)
            return {
                "job_id": effective_job_id,
                "queries": queries,
                "search": search,
                "sources": registered_sources or downloadable_sources,
                "answer": answer_payload,
            }

        update_job(effective_job_id, status="failed", progress=1.0, message="research failed", error=str(exc))
        append_job_event(
            effective_job_id,
            "research_failed",
            {
                "status": "failed",
                "phase": "failed",
                "message": "research failed",
                "error": str(exc),
                "progress": 1.0,
                "updated_at": _now_iso(),
            },
        )
        _record_state(effective_job_id, "failed", message=str(exc), progress=1.0)
        raise
