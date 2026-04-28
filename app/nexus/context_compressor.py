from __future__ import annotations

from dataclasses import dataclass
import math
import os
import re
from collections import defaultdict


PROFILE_ORDER = ["compact_8k", "standard_16k", "high_24k", "extended_32k"]


@dataclass(frozen=True)
class CompressionProfile:
    name: str
    max_evidence_tokens: int
    max_evidence_chunks: int
    max_chars_per_chunk: int
    max_evidence_chars: int
    max_source_tokens: int


PROFILES: dict[str, CompressionProfile] = {
    "compact_8k": CompressionProfile(
        "compact_8k",
        max_evidence_tokens=4500,
        max_evidence_chunks=10,
        max_chars_per_chunk=800,
        max_evidence_chars=9000,
        max_source_tokens=1800,
    ),
    "standard_16k": CompressionProfile(
        "standard_16k",
        max_evidence_tokens=10500,
        max_evidence_chunks=20,
        max_chars_per_chunk=1200,
        max_evidence_chars=16000,
        max_source_tokens=3000,
    ),
    "high_24k": CompressionProfile(
        "high_24k",
        max_evidence_tokens=16500,
        max_evidence_chunks=32,
        max_chars_per_chunk=1400,
        max_evidence_chars=28000,
        max_source_tokens=5600,
    ),
    "extended_32k": CompressionProfile(
        "extended_32k",
        max_evidence_tokens=23000,
        max_evidence_chunks=48,
        max_chars_per_chunk=1600,
        max_evidence_chars=42000,
        max_source_tokens=7600,
    ),
}


@dataclass(frozen=True)
class ContextBudget:
    max_context_tokens: int
    reserved_output_tokens: int
    safety_tokens: int
    max_evidence_tokens: int
    max_evidence_chars: int
    max_evidence_chunks: int
    max_chars_per_chunk: int
    max_source_tokens: int
    max_chunks_per_source: int
    auto_budget: bool
    compression_profile: str


_WORD_RE = re.compile(r"[\w\u3040-\u30ff\u3400-\u9fff]+", re.UNICODE)


def estimate_tokens(text: str) -> int:
    raw = str(text or "")
    if not raw:
        return 0
    # 日英混在をやや保守的に見積もる
    return max(1, int(math.ceil(len(raw) / 2.5)) + 8)


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(str(text or "")) if len(m.group(0)) >= 2}


def _source_quality_weight(source_type: str) -> float:
    key = str(source_type or "").strip().lower()
    if key == "official":
        return 1.25
    if key == "paper":
        return 1.2
    if key == "news":
        return 1.05
    if key == "market":
        return 1.0
    if key == "library":
        return 0.95
    return 0.9


def _normalize_quote(text: str) -> str:
    q = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return q[:400]


def choose_profile_name(ctx_tokens: int) -> str:
    if ctx_tokens >= 32768:
        return "extended_32k"
    if ctx_tokens >= 24576:
        return "high_24k"
    if ctx_tokens >= 16384:
        return "standard_16k"
    return "compact_8k"


def stronger_profile(current: str) -> str:
    if current not in PROFILE_ORDER:
        return "compact_8k"
    idx = PROFILE_ORDER.index(current)
    return PROFILE_ORDER[max(0, idx - 1)]


def build_context_budget(
    *,
    max_context_tokens: int,
    instruction_tokens_estimate: int,
    question_tokens_estimate: int,
    source_metadata_tokens_estimate: int,
    preferred_profile: str | None = None,
) -> ContextBudget:
    ctx = max(2048, int(max_context_tokens or 16384))
    auto_budget = str(os.environ.get("NEXUS_ANSWER_LLM_AUTO_BUDGET", "true")).strip().lower() not in {"0", "false", "no", "off"}

    env_reserved = str(os.environ.get("NEXUS_ANSWER_LLM_RESERVED_OUTPUT_TOKENS", "")).strip()
    env_safety = str(os.environ.get("NEXUS_ANSWER_LLM_CONTEXT_SAFETY_TOKENS", "")).strip()
    reserved_default = 2048 if ctx >= 24576 else 1536
    safety_default = 1800 if ctx >= 24576 else 1200
    reserved = int(env_reserved) if env_reserved.isdigit() else reserved_default
    safety = int(env_safety) if env_safety.isdigit() else safety_default

    profile_name = preferred_profile or choose_profile_name(ctx)
    profile = PROFILES.get(profile_name, PROFILES["standard_16k"])

    available = ctx - reserved - safety - max(0, instruction_tokens_estimate) - max(0, question_tokens_estimate) - max(0, source_metadata_tokens_estimate)
    available = max(1000, available)

    env_max_ev = str(os.environ.get("NEXUS_ANSWER_LLM_MAX_EVIDENCE_TOKENS", "")).strip()
    max_evidence_tokens = int(env_max_ev) if env_max_ev.isdigit() else profile.max_evidence_tokens
    if auto_budget:
        max_evidence_tokens = min(max_evidence_tokens, available)

    env_chars = str(os.environ.get("NEXUS_ANSWER_LLM_MAX_EVIDENCE_CHARS", "")).strip()
    env_chunks = str(os.environ.get("NEXUS_ANSWER_LLM_MAX_EVIDENCE_CHUNKS", "")).strip()
    env_chunk_chars = str(os.environ.get("NEXUS_ANSWER_LLM_MAX_CHARS_PER_CHUNK", "")).strip()
    env_source_tok = str(os.environ.get("NEXUS_ANSWER_LLM_MAX_SOURCE_TOKENS", "")).strip()
    env_chunks_per_source = str(os.environ.get("NEXUS_ANSWER_LLM_MAX_CHUNKS_PER_SOURCE", "5")).strip()

    return ContextBudget(
        max_context_tokens=ctx,
        reserved_output_tokens=reserved,
        safety_tokens=safety,
        max_evidence_tokens=max(500, max_evidence_tokens),
        max_evidence_chars=max(1000, int(env_chars) if env_chars.isdigit() else profile.max_evidence_chars),
        max_evidence_chunks=max(1, int(env_chunks) if env_chunks.isdigit() else profile.max_evidence_chunks),
        max_chars_per_chunk=max(200, int(env_chunk_chars) if env_chunk_chars.isdigit() else profile.max_chars_per_chunk),
        max_source_tokens=max(300, int(env_source_tok) if env_source_tok.isdigit() else profile.max_source_tokens),
        max_chunks_per_source=max(1, int(env_chunks_per_source) if env_chunks_per_source.isdigit() else 5),
        auto_budget=auto_budget,
        compression_profile=profile.name,
    )


def compress_large_source(query: str, source: dict, chunks: list[dict], budget: ContextBudget) -> dict:
    q_terms = _tokenize(query)
    scored: list[tuple[float, dict]] = []
    for idx, chunk in enumerate(chunks):
        quote = str(chunk.get("quote") or chunk.get("text") or "")
        terms = _tokenize(quote)
        overlap = len(q_terms & terms)
        score = float(overlap)
        score += min(1.0, len(quote) / 1200.0)
        score += _source_quality_weight(str(source.get("source_type") or chunk.get("source_type") or "web"))
        score += (0.0001 * (len(chunks) - idx))
        row = dict(chunk)
        row["_score"] = score
        scored.append((score, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    picked: list[dict] = []
    used_chunk_ids: set[str] = set()
    used_tokens = 0

    best_score = scored[0][0] if scored else 0.0
    high_relevance = best_score >= 3.0
    source_limit = int(budget.max_evidence_tokens * (0.40 if high_relevance else 0.25))
    source_limit = min(max(300, source_limit), budget.max_source_tokens)

    chunk_index: dict[str, int] = {}
    for idx, chunk in enumerate(chunks):
        cid = str(chunk.get("chunk_id") or f"idx-{idx}")
        chunk_index[cid] = idx

    for _, chunk in scored:
        if len(picked) >= budget.max_chunks_per_source:
            break
        text = str(chunk.get("quote") or chunk.get("text") or "")
        cid = str(chunk.get("chunk_id") or "")
        if cid and cid in used_chunk_ids:
            continue
        trimmed = text[: budget.max_chars_per_chunk]
        tok = estimate_tokens(trimmed)
        if used_tokens + tok > source_limit:
            continue
        row = dict(chunk)
        row["quote"] = trimmed
        picked.append(row)
        used_tokens += tok
        if cid:
            used_chunk_ids.add(cid)

        # 近傍を少し追加
        if cid and cid in chunk_index and len(picked) < budget.max_chunks_per_source:
            pos = chunk_index[cid]
            for neighbor_pos in (pos - 1, pos + 1):
                if neighbor_pos < 0 or neighbor_pos >= len(chunks):
                    continue
                neighbor = dict(chunks[neighbor_pos])
                n_cid = str(neighbor.get("chunk_id") or "")
                if n_cid and n_cid in used_chunk_ids:
                    continue
                n_txt = str(neighbor.get("quote") or neighbor.get("text") or "")[: budget.max_chars_per_chunk]
                n_tok = estimate_tokens(n_txt)
                if used_tokens + n_tok > source_limit:
                    continue
                neighbor["quote"] = n_txt
                picked.append(neighbor)
                used_tokens += n_tok
                if n_cid:
                    used_chunk_ids.add(n_cid)
                break

    return {
        "source": {
            "source_id": str(source.get("source_id") or ""),
            "source_type": str(source.get("source_type") or "web"),
            "publisher": str(source.get("publisher") or ""),
            "title": str(source.get("title") or ""),
            "url": str(source.get("url") or source.get("final_url") or ""),
            "source_note": f"compressed:{len(chunks)}->{len(picked)}",
        },
        "chunks": picked,
        "tokens": used_tokens,
        "high_relevance": high_relevance,
    }


def compress_global_evidence(query: str, references: list[dict], evidence_chunks: list[dict], budget: ContextBudget) -> dict:
    source_map: dict[str, dict] = {str(r.get("source_id") or ""): dict(r) for r in references}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for chunk in evidence_chunks:
        source_id = str(chunk.get("source_id") or "")
        grouped[source_id].append(dict(chunk))

    packets: list[dict] = []
    large_sources = 0
    for source_id, chunks in grouped.items():
        source = source_map.get(source_id, {"source_id": source_id, "source_type": str(chunks[0].get("source_type") or "web") if chunks else "web"})
        packet = compress_large_source(query, source, chunks, budget)
        if len(chunks) > len(packet["chunks"]):
            large_sources += 1
        packets.append(packet)

    q_terms = _tokenize(query)
    for packet in packets:
        stype = str(packet["source"].get("source_type") or "web").lower()
        text = " ".join(str(c.get("quote") or c.get("text") or "") for c in packet.get("chunks", []))
        overlap = len(q_terms & _tokenize(text))
        packet["_rank"] = overlap + _source_quality_weight(stype)

    packets.sort(key=lambda p: p.get("_rank", 0.0), reverse=True)

    selected_packets: list[dict] = []
    selected_chunks: list[dict] = []
    selected_refs: list[dict] = []
    used_tokens = 0
    used_chars = 0
    used_quote_norm: set[str] = set()
    used_urls: set[str] = set()
    used_titles: set[str] = set()
    dropped: list[dict] = []
    bucket_seen: set[str] = set()
    compression_empty_fallback_used = False

    # diversity first pass
    diverse_first: list[dict] = []
    rest: list[dict] = []
    for packet in packets:
        stype = str(packet["source"].get("source_type") or "web").lower()
        if stype not in bucket_seen:
            bucket_seen.add(stype)
            diverse_first.append(packet)
        else:
            rest.append(packet)

    for packet in [*diverse_first, *rest]:
        source = packet["source"]
        src_url = str(source.get("url") or "")
        src_title = str(source.get("title") or "")
        source_chunks = packet.get("chunks", [])
        if not source_chunks:
            dropped.append({"source_id": source.get("source_id"), "reason": "empty_after_source_compression"})
            continue
        if src_url and src_url in used_urls:
            dropped.append({"source_id": source.get("source_id"), "reason": "duplicate_url"})
            continue
        if src_title and src_title.lower() in used_titles:
            dropped.append({"source_id": source.get("source_id"), "reason": "duplicate_title"})
            continue

        candidate_chunks: list[dict] = []
        candidate_tokens = 0
        candidate_chars = 0
        for chunk in source_chunks:
            quote = str(chunk.get("quote") or chunk.get("text") or "")[: budget.max_chars_per_chunk]
            qnorm = _normalize_quote(quote)
            if qnorm and qnorm in used_quote_norm:
                continue
            tok = estimate_tokens(quote)
            if used_tokens + candidate_tokens + tok > budget.max_evidence_tokens:
                continue
            if used_chars + candidate_chars + len(quote) > budget.max_evidence_chars:
                continue
            if len(selected_chunks) + len(candidate_chunks) >= budget.max_evidence_chunks:
                continue
            row = dict(chunk)
            row["quote"] = quote
            candidate_chunks.append(row)
            candidate_tokens += tok
            candidate_chars += len(quote)
            if qnorm:
                used_quote_norm.add(qnorm)

        if not candidate_chunks:
            dropped.append({"source_id": source.get("source_id"), "reason": "global_budget_or_dedupe"})
            continue

        used_tokens += candidate_tokens
        used_chars += candidate_chars
        selected_packets.append(packet)
        selected_chunks.extend(candidate_chunks)
        ref = dict(source)
        selected_refs.append(ref)
        if src_url:
            used_urls.add(src_url)
        if src_title:
            used_titles.add(src_title.lower())
        if used_tokens >= budget.max_evidence_tokens or len(selected_chunks) >= budget.max_evidence_chunks:
            break

    if not selected_chunks and evidence_chunks:
        # 圧縮結果が空なら、巨大入力へ戻さず最小短縮セットを作る。
        mini_refs_by_source: dict[str, dict] = {}
        for raw in evidence_chunks:
            if len(selected_chunks) >= min(3, budget.max_evidence_chunks):
                break
            source_id = str(raw.get("source_id") or "")
            mini_quote = str(raw.get("quote") or raw.get("text") or "").strip()[: min(220, budget.max_chars_per_chunk)]
            if not mini_quote:
                continue
            tok = estimate_tokens(mini_quote)
            if used_tokens + tok > budget.max_evidence_tokens or used_chars + len(mini_quote) > budget.max_evidence_chars:
                continue
            mini = dict(raw)
            mini["quote"] = mini_quote
            selected_chunks.append(mini)
            used_tokens += tok
            used_chars += len(mini_quote)
            if source_id and source_id not in mini_refs_by_source:
                mini_refs_by_source[source_id] = dict(source_map.get(source_id, {"source_id": source_id, "source_type": str(raw.get("source_type") or "web")}))
        if selected_chunks:
            compression_empty_fallback_used = True
            selected_refs = list(mini_refs_by_source.values())

    selected_source_types = sorted(
        {
            str(ref.get("source_type") or "").strip().lower()
            for ref in selected_refs
            if str(ref.get("source_type") or "").strip()
        }
    )
    stats = {
        "sources_input": len(grouped),
        "sources_used": len(selected_refs),
        "chunks_input": len(evidence_chunks),
        "chunks_used": len(selected_chunks),
        "estimated_evidence_tokens": used_tokens,
        "evidence_chars_used": used_chars,
        "evidence_truncated": len(selected_chunks) < len(evidence_chunks),
        "large_sources_compressed": large_sources,
        "global_budget_applied": True,
        "dropped_count": len(dropped),
        "dropped": dropped[:200],
        "max_evidence_chars": budget.max_evidence_chars,
        "max_source_tokens": budget.max_source_tokens,
        "max_chars_per_chunk": budget.max_chars_per_chunk,
        "compression_empty_fallback_used": compression_empty_fallback_used,
        "selected_source_types": selected_source_types,
    }
    return {
        "references": selected_refs,
        "chunks": selected_chunks,
        "packets": selected_packets,
        "stats": stats,
    }
