from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime, timezone
import re
import threading
import time
import uuid
from typing import Any

from app.nexus.answer_builder import build_answer_payload
from app.nexus.citation_mapper import build_citation_map, normalize_reference_labels
from app.nexus.config import load_runtime_config
from app.nexus.downloader import safe_download, save_download_artifacts
from app.nexus.evidence import EvidenceItem, replace_evidence_items_for_job, save_evidence_items
from app.nexus.jobs import append_job_event, append_job_heartbeat, create_job, ensure_job_exists, update_job
from app.nexus.source_collector import collect_source_candidates, rank_source_candidates
from app.nexus.source_registry import (
    canonicalize_source_url,
    find_reusable_artifact,
    register_or_update_sources,
    upsert_source_artifact,
)
from app.nexus.db import get_conn
from app.nexus.web_scout import plan_web_queries, run_web_search


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



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
    return {
        "confidence": confidence,
        "sufficient": len(gaps) == 0,
        "gaps": gaps,
        "unresolved_items": unresolved_items,
    }


def _generate_followup_queries(*, original_query: str, gaps: list[str], max_followup_queries: int) -> list[str]:
    gap_hints = {
        "source_count_low": "最新 統計 公式データ",
        "evidence_chunks_low": "詳細 レポート PDF",
        "official_or_pdf_missing": "site:gov OR site:org filetype:pdf",
        "answer_contains_unverified": "検証 ファクトチェック 一次情報",
        "high_degraded_or_failed_ratio": "ミラー 公的機関 代替ソース",
        "citation_count_low": "根拠 出典",
    }
    queries: list[str] = []
    seen: set[str] = set()
    for gap in gaps:
        hint = gap_hints.get(gap)
        if not hint:
            continue
        q = f"{original_query} {hint}".strip()
        if q in seen:
            continue
        seen.add(q)
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
        create_job(effective_job_id, title=query, message="research queued", status="queued")
    else:
        ensure_job_exists(effective_job_id, title=query, message="research queued", status="queued")

    try:
        _emit_phase(effective_job_id, "planning_started", phase="planning", message="planning started", progress=0.05)
        _record_state(effective_job_id, "planning", message="query planning", progress=0.1)
        queries = plan_web_queries(
            query,
            mode=payload.mode,
            depth=payload.depth,
            max_queries=payload.max_queries,
            scope=payload.scope,
            language=payload.language,
        )
        _emit_phase(
            effective_job_id,
            "planning_finished",
            phase="planning",
            message="planning finished",
            progress=0.2,
            details={"queries": len(queries)},
        )
        update_job(effective_job_id, status="running", progress=0.2, message="searching web")

        _emit_phase(effective_job_id, "web_search_started", phase="web_search", message="web search started", progress=0.22)
        _record_state(effective_job_id, "searching", message="running web search", progress=0.25)
        search = run_web_search(
            queries,
            mode=payload.mode,
            depth=payload.depth,
            max_results_per_query=payload.max_results_per_query,
            scope=payload.scope,
            language=payload.language,
        )
        items = list(search.get("items") or [])
        _emit_phase(
            effective_job_id,
            "web_search_finished",
            phase="web_search",
            message="web search finished",
            progress=0.35,
            details={"result_count": len(items)},
        )

        _emit_phase(
            effective_job_id, "source_collection_started", phase="source_collection", message="source collection started", progress=0.36
        )
        _record_state(effective_job_id, "collecting_sources", message="normalizing source candidates", progress=0.4)
        candidates = collect_source_candidates(search_items=items, manual_urls=payload.manual_urls)
        ranked_candidates = rank_source_candidates(
            candidates,
            prefer_pdf=payload.prefer_pdf,
            official_first=payload.official_first,
        )
        if len(ranked_candidates) > max_sources:
            append_job_event(
                effective_job_id,
                "constraint_applied",
                {
                    "status": "running",
                    "progress": 0.45,
                    "message": f"candidate limit reached: max_sources={max_sources}",
                    "reason": "max_sources_exceeded",
                    "max_download_mb": max_download_mb,
                    "max_download_bytes": max_download_bytes,
                    "max_sources": max_sources,
                    "candidate_count": len(ranked_candidates),
                },
            )
            ranked_candidates = ranked_candidates[:max_sources]
        _emit_phase(
            effective_job_id,
            "source_collection_finished",
            phase="source_collection",
            message="source collection finished",
            progress=0.5,
            details={"candidate_count": len(ranked_candidates)},
        )
        _record_state(effective_job_id, "downloading", message="downloading source content", progress=0.55)
        _emit_phase(
            effective_job_id,
            "download_phase_started",
            phase="downloading",
            message="download phase started",
            progress=0.55,
            details={"total_candidates": len(ranked_candidates)},
        )
        downloadable_sources, download_error_count = _download_sources_parallel(
            job_id=effective_job_id,
            candidates=ranked_candidates,
            max_downloads=max_downloads,
            max_download_bytes=max_download_bytes,
            max_total_download_bytes=max_total_download_bytes,
            download_timeout_sec=download_timeout_sec,
            continue_on_download_error=payload.continue_on_download_error,
            concurrency=runtime_cfg.download_concurrency,
            pdf_extract_concurrency=runtime_cfg.pdf_extract_concurrency,
            download_progress_interval_sec=runtime_cfg.download_progress_interval_sec,
            download_stalled_after_sec=runtime_cfg.download_stalled_after_sec,
        )
        _emit_phase(
            effective_job_id,
            "download_phase_finished",
            phase="downloading",
            message="download phase finished",
            progress=0.65,
            details={"download_count": sum(1 for s in downloadable_sources if str(s.get("status")) in {"downloaded", "ingested"}), "download_errors": download_error_count},
        )

        _emit_phase(effective_job_id, "source_ingest_started", phase="source_ingest", message="source ingest started", progress=0.66)
        registered_sources = register_or_update_sources(
            job_id=effective_job_id,
            project=payload.project,
            sources=downloadable_sources,
        )

        evidence_items = _build_evidence_from_sources(effective_job_id, registered_sources)
        save_evidence_items(effective_job_id, evidence_items)
        _emit_phase(
            effective_job_id,
            "source_ingest_finished",
            phase="source_ingest",
            message="source ingest finished",
            progress=0.69,
            details={"source_count": len(registered_sources)},
        )

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

        _record_state(effective_job_id, "answering", message="building answer", progress=0.85)
        _emit_phase(
            effective_job_id,
            "answer_llm_request_started",
            phase="answer_llm_generating",
            message="answer llm request started",
            progress=0.84,
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
        answer_payload["recursive_search"] = bool(payload.recursive_search)
        answer_payload["iterations"] = iterations
        answer_payload["confidence"] = final_confidence
        answer_payload["unresolved_items"] = unresolved_items
        answer_payload["stop_reason"] = stop_reason
        answer_payload["recursive_stop_reason"] = recursive_stop_reason
        answer_payload["followup_search_count"] = followup_search_count
        answer_payload["followup_queries_count"] = followup_queries_count
        answer_payload["added_sources_total"] = added_sources_total
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
        if download_error_count > 0:
            update_job(
                effective_job_id,
                status="degraded",
                progress=1.0,
                message="research completed with degraded downloads",
            )
            append_job_event(
                effective_job_id,
                "job_degraded",
                {
                    "status": "degraded",
                    "progress": 1.0,
                    "message": "research completed with degraded downloads",
                    "download_error_count": download_error_count,
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
        else:
            update_job(effective_job_id, status="completed", progress=1.0, message="research completed")
            _emit_phase(
                effective_job_id,
                "job_completed",
                phase="completed",
                message="job completed",
                progress=1.0,
                status="completed",
            )
            _record_state(effective_job_id, "completed", message="job completed", progress=1.0)

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
        _emit_phase(
            effective_job_id,
            "job_failed",
            phase="failed",
            message=str(exc),
            progress=1.0,
            status="failed",
            details={"error": str(exc)},
        )
        _record_state(effective_job_id, "failed", message=str(exc), progress=1.0)
        raise
