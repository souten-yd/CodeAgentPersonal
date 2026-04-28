from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
from urllib import error, request
import uuid

from app.nexus.config import NEXUS_PATHS
from app.nexus.context_compressor import (
    build_context_budget,
    choose_profile_name,
    compress_global_evidence,
    estimate_tokens,
    stronger_profile,
)
from app.nexus.citation_mapper import normalize_reference_labels, replace_citation_labels
from app.nexus.db import transaction
from app.nexus.citation_verifier import CitationSupportVerifier, verify_citation_labels
from app.nexus.utils import ensure_dir

logger = logging.getLogger(__name__)


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


def _llm_answer_enabled() -> bool:
    settings = _resolve_answer_llm_settings()
    return bool(settings.get("enabled"))


def _llm_endpoint() -> str:
    settings = _resolve_answer_llm_settings()
    return str(settings.get("endpoint") or "").strip()


def _llm_model() -> str:
    settings = _resolve_answer_llm_settings()
    return str(settings.get("model") or "local-llm").strip() or "local-llm"


def _env_truthy(name: str) -> bool | None:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return None
    return raw in {"1", "true", "yes", "on", "enabled"}


def _normalize_chat_completions_endpoint(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        return ""
    if value.endswith("/v1/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value.rstrip("/") + "/v1/chat/completions"


def _build_endpoint_candidates() -> list[str]:
    openai_base = str(os.environ.get("OPENAI_BASE_URL", "")).strip()
    search_assignment = _load_search_role_assignment()
    search_endpoint = _normalize_chat_completions_endpoint(
        str(search_assignment.get("endpoint") or search_assignment.get("base_url") or "").strip()
    )
    candidates = [
        str(os.environ.get("DEEP_RESEARCH_LLM_ENDPOINT", "")).strip(),
        str(os.environ.get("ANSWER_LLM_ENDPOINT", "")).strip(),
        str(os.environ.get("NEXUS_ANSWER_LLM_ENDPOINT", "")).strip(),
        search_endpoint,
        _normalize_chat_completions_endpoint(openai_base) if openai_base else "",
        str(os.environ.get("LOCAL_LLM_ENDPOINT", "")).strip(),
        str(os.environ.get("CODEAGENT_LLM_CHAT", "")).strip(),
        str(os.environ.get("LLM_URL", "")).strip(),
        "http://127.0.0.1:8080/v1/chat/completions",
    ]
    deduped: list[str] = []
    for candidate in candidates:
        normalized = _normalize_chat_completions_endpoint(candidate)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _probe_llm_endpoint_detail(endpoint: str, timeout_sec: float = 1.5) -> dict:
    if not endpoint:
        return {
            "endpoint": "",
            "reachable": False,
            "checks": [],
            "error": "empty endpoint",
        }
    base = endpoint.replace("/v1/chat/completions", "").rstrip("/")
    probe_urls = [f"{base}/v1/models", f"{base}/health"]
    checks: list[dict] = []

    def _is_success(status: int) -> bool:
        return 200 <= status < 300 or status in {401, 403}

    for probe_url in probe_urls:
        req = request.Request(probe_url, method="GET")
        status = 0
        err_text = ""
        try:
            with request.urlopen(req, timeout=timeout_sec) as resp:
                status = int(getattr(resp, "status", 0))
        except error.HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            err_text = f"http_error:{status}"
        except Exception as exc:  # noqa: BLE001
            err_text = str(exc)

        check = {
            "url": probe_url,
            "status": status,
            "ok": _is_success(status),
            "error": err_text,
        }
        checks.append(check)
        logger.info("answer llm probe url=%s status=%s ok=%s error=%s", probe_url, status, check["ok"], err_text)
        if check["ok"]:
            return {
                "endpoint": endpoint,
                "reachable": True,
                "checks": checks,
                "error": "",
            }

    last_error = ""
    for check in checks:
        if check.get("error"):
            last_error = str(check.get("error"))
            break
    if not last_error and checks:
        last_error = f"http_status:{checks[-1].get('status')}"
    return {
        "endpoint": endpoint,
        "reachable": False,
        "checks": checks,
        "error": last_error,
    }


def _probe_llm_endpoint(endpoint: str, timeout_sec: float = 1.5) -> bool:
    return bool(_probe_llm_endpoint_detail(endpoint=endpoint, timeout_sec=timeout_sec).get("reachable"))


def _default_model_db_path() -> Path:
    configured = str(os.environ.get("CODEAGENT_MODEL_DB_PATH", "")).strip()
    if configured:
        return Path(configured)
    ca_data_dir = str(os.environ.get("CODEAGENT_CA_DATA_DIR", "")).strip()
    if ca_data_dir:
        return Path(ca_data_dir) / "model_db.db"
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "ca_data" / "model_db.db"


def _load_search_role_assignment() -> dict:
    db_path = _default_model_db_path()
    if not db_path.exists():
        return {}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        role_row = conn.execute("SELECT value FROM settings WHERE key = ?", ("role_model_search",)).fetchone()
        if role_row is None:
            return {"role": "SEARCH", "error": "role_model_search_unset"}
        model_key = str(role_row["value"] or "").strip()
        if not model_key:
            return {"role": "SEARCH", "error": "role_model_search_empty"}
        model_row = conn.execute(
            "SELECT model_key, enabled, llm_url, name, ctx_size FROM models WHERE model_key = ? LIMIT 1",
            (model_key,),
        ).fetchone()
        if model_row is None:
            return {"role": "SEARCH", "model_key": model_key, "error": "search_model_not_found"}
        return {
            "role": "SEARCH",
            "model_key": str(model_row["model_key"] or "").strip(),
            "model": str(model_row["model_key"] or "").strip(),
            "name": str(model_row["name"] or "").strip(),
            "enabled": int(model_row["enabled"] or 0) != 0,
            "endpoint": str(model_row["llm_url"] or "").strip(),
            "base_url": str(model_row["llm_url"] or "").strip(),
            "ctx_size": int(model_row["ctx_size"] or 0),
        }
    except Exception as exc:  # noqa: BLE001
        return {"role": "SEARCH", "error": f"search_role_lookup_failed:{exc}"}
    finally:
        if conn is not None:
            conn.close()


def _discover_model_from_models_api(endpoint: str, timeout_sec: float = 1.5) -> str:
    if not endpoint:
        return ""
    base = endpoint.replace("/v1/chat/completions", "").rstrip("/")
    models_url = f"{base}/v1/models"
    req = request.Request(models_url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, list) or not data:
        return ""
    first = data[0] if isinstance(data[0], dict) else {}
    return str(first.get("id") or "").strip()


def _resolve_model_name(*, endpoint: str, search_assignment: dict) -> tuple[str, str, str]:
    explicit_model = str(os.environ.get("DEEP_RESEARCH_LLM_MODEL", "")).strip()
    if explicit_model:
        return explicit_model, "explicit", "deep_research_llm_model"
    answer_model = str(os.environ.get("ANSWER_LLM_MODEL", "")).strip()
    if answer_model:
        return answer_model, "explicit", "answer_llm_model"
    nexus_answer_model = str(os.environ.get("NEXUS_ANSWER_LLM_MODEL", "")).strip()
    if nexus_answer_model:
        return nexus_answer_model, "explicit", "nexus_answer_llm_model"

    search_model = str(search_assignment.get("model") or "").strip()
    search_enabled = bool(search_assignment.get("enabled"))
    if search_model and search_enabled:
        return search_model, "model_orchestrator", "search_role_model"
    if str(search_assignment.get("error") or "").strip():
        search_reason = str(search_assignment.get("error") or "").strip()
    else:
        search_reason = "search_role_model_missing_or_disabled"

    llm_model = str(os.environ.get("LLM_MODEL", "")).strip()
    if llm_model:
        return llm_model, "fallback", f"{search_reason}_fallback_to_llm_model"

    first_model = _discover_model_from_models_api(endpoint)
    if first_model:
        return first_model, "fallback", f"{search_reason}_fallback_to_models_api"
    return "local-llm", "fallback", f"{search_reason}_fallback_to_local_llm"


def _resolve_answer_llm_settings() -> dict:
    endpoint_candidates = _build_endpoint_candidates()
    explicit_endpoint = str(os.environ.get("DEEP_RESEARCH_LLM_ENDPOINT", "")).strip()
    explicit_endpoint = _normalize_chat_completions_endpoint(explicit_endpoint) if explicit_endpoint else ""
    search_assignment = _load_search_role_assignment()

    explicit_enabled = (
        _env_truthy("DEEP_RESEARCH_LLM_ENABLED")
        if _env_truthy("DEEP_RESEARCH_LLM_ENABLED") is not None
        else (
            _env_truthy("ANSWER_LLM_ENABLED")
            if _env_truthy("ANSWER_LLM_ENABLED") is not None
            else (
                _env_truthy("NEXUS_ENABLE_ANSWER_LLM")
                if _env_truthy("NEXUS_ENABLE_ANSWER_LLM") is not None
                else _env_truthy("LLM_ENABLED")
            )
        )
    )
    if explicit_enabled is not None:
        enabled = explicit_enabled and bool(endpoint_candidates)
    else:
        enabled = False

    selected_endpoint = endpoint_candidates[0] if endpoint_candidates else ""
    selected_reason = "no_candidates"
    probe_status: list[dict] = []
    first_reachable: dict | None = None
    for idx, candidate in enumerate(endpoint_candidates):
        detail = _probe_llm_endpoint_detail(candidate)
        detail["index"] = idx
        probe_status.append(detail)
        if first_reachable is None and bool(detail.get("reachable")):
            first_reachable = detail
            selected_endpoint = str(detail.get("endpoint") or candidate)
            selected_reason = "first_reachable_candidate"
            break

    if first_reachable is None and endpoint_candidates:
        selected_endpoint = endpoint_candidates[0]
        selected_reason = "all_candidates_unreachable"
    elif first_reachable is not None and explicit_endpoint:
        if selected_endpoint == explicit_endpoint:
            selected_reason = "explicit_endpoint_reachable"
        else:
            selected_reason = "explicit_endpoint_unreachable_fallback_candidate"

    llm_reachable = bool(first_reachable and first_reachable.get("reachable"))
    probe_error = ""
    if first_reachable is None and probe_status:
        probe_error = "all endpoint probes failed"
        logger.warning(
            "answer llm probes failed candidates=%s details=%s",
            endpoint_candidates,
            probe_status,
        )
    elif first_reachable is not None:
        probe_error = str(first_reachable.get("error") or "")

    if explicit_enabled is None:
        enabled = bool(selected_endpoint) and llm_reachable

    model, model_source, model_reason = _resolve_model_name(
        endpoint=selected_endpoint,
        search_assignment=search_assignment,
    )
    selected_reason = model_reason if model_source != "model_orchestrator" else "search_role_model"

    return {
        "enabled": enabled,
        "endpoint": selected_endpoint,
        "model": model,
        "model_role": "SEARCH",
        "model_source": model_source,
        "reachable": llm_reachable,
        "probe_error": probe_error,
        "selected_reason": selected_reason,
        "probe_status": probe_status,
        "explicit_enabled": explicit_enabled,
        "search_assignment": search_assignment,
    }


def _looks_like_context_overflow_error(message: str) -> bool:
    text = str(message or "").lower()
    markers = (
        "exceed_context_size_error",
        "exceeds the available context size",
        "n_prompt_tokens",
        "n_ctx",
    )
    return any(marker in text for marker in markers)


def _first_positive_int(*values: object) -> int | None:
    for value in values:
        try:
            parsed = int(str(value).strip())
        except Exception:  # noqa: BLE001
            continue
        if parsed > 0:
            return parsed
    return None


def _fetch_context_tokens_from_models_api(endpoint: str, model_name: str, timeout_sec: float = 1.5) -> int | None:
    if not endpoint:
        return None
    base = endpoint.replace("/v1/chat/completions", "").rstrip("/")
    models_url = f"{base}/v1/models"
    req = request.Request(models_url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, list):
        return None

    selected: dict | None = None
    for row in data:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "").strip() == model_name:
            selected = row
            break
    if selected is None and data and isinstance(data[0], dict):
        selected = data[0]
    if not selected:
        return None

    context_fields = (
        selected.get("context_length"),
        selected.get("max_context_tokens"),
        (selected.get("metadata") or {}).get("context_length") if isinstance(selected.get("metadata"), dict) else None,
    )
    return _first_positive_int(*context_fields)


def _generate_answer_with_llm(
    *,
    question: str,
    references: list[dict],
    evidence_chunks: list[dict],
    timeout_sec: float | None = None,
    llm_settings: dict | None = None,
) -> str:
    llm_settings = llm_settings or _resolve_answer_llm_settings()
    if not bool(llm_settings.get("enabled")):
        raise RuntimeError("answer llm is disabled")

    endpoint = str(llm_settings.get("endpoint") or "").strip()
    model = str(llm_settings.get("model") or "").strip() or "local-llm"
    timeout_value = float(timeout_sec or os.environ.get("NEXUS_ANSWER_LLM_TIMEOUT_SEC", "20"))
    max_tokens = int(str(os.environ.get("NEXUS_ANSWER_LLM_MAX_TOKENS", "1024")).strip() or "1024")

    reference_lines = []
    for idx, ref in enumerate(references, start=1):
        label = str(ref.get("citation_label") or f"[S{idx}]")
        title = str(ref.get("title") or ref.get("url") or "(untitled)")
        reference_lines.append(f"- {label} {title}")
    evidence_lines = []
    for chunk in evidence_chunks:
        citation_label = str(chunk.get("citation_label") or "").strip() or "未確認"
        source_id = str(chunk.get("source_id") or "").strip() or "unknown"
        quote_text = str(chunk.get("quote") or chunk.get("text") or "").strip()
        if quote_text:
            evidence_lines.append(f"- {citation_label} source={source_id}: {quote_text}")

    system_prompt = (
        "あなたは調査回答アシスタントです。必ず根拠に基づいて日本語で回答してください。"
        "Evidence 以外を根拠に断定しないこと。"
        "重要主張ごとに [S1] 形式のcitationを必ず付与すること。"
        "未確認事項は必ず「未確認」と明記すること。"
        "回答末尾に「追加確認が必要な点」セクションを必ず出力すること。"
    )
    user_prompt = "\n".join(
        [
            f"質問:\n{question}",
            "",
            "参考ソース:",
            *reference_lines,
            "",
            "Evidence:",
            *(evidence_lines or ["- 未確認: 提示できるevidence chunkがありません。"]),
            "",
            "出力形式:",
            "- 冒頭に簡潔な結論",
            "- 主要な主張ごとに citation ([S1] など) を付ける",
            "- 未確認事項には「未確認」と記載",
            "- 最後に必ず「## 追加確認が必要な点」セクション",
        ]
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req, timeout=timeout_value) as resp:
            raw = resp.read().decode("utf-8")
    except TimeoutError as exc:
        raise TimeoutError("answer llm timeout") from exc
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            body = ""
        raise RuntimeError(f"answer llm http_error: status={exc.code} body={body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"answer llm unavailable: {exc}") from exc

    parsed = json.loads(raw)
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("llm response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = str(content or "").strip()
    if not text:
        raise ValueError("llm returned empty answer")
    return text


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
    answer_payload: dict,
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
                answer_markdown, evidence_json, answer_json, source_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                job_id,
                project,
                question,
                answer_markdown,
                json.dumps(evidence_json, ensure_ascii=False),
                json.dumps(answer_payload, ensure_ascii=False),
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
    evidence_chunks: list[dict] | None = None,
    job_id: str | None = None,
    project: str = "default",
    citation_support_verifier: CitationSupportVerifier | None = None,
) -> dict:
    normalized = normalize_reference_labels(
        references=references,
        evidence_json=evidence,
        evidence_chunks=evidence_chunks,
    )
    normalized_references = normalized["references"]
    normalized_evidence_json = normalized["evidence_json"]
    normalized_chunks = normalized["evidence_chunks"]

    summary_text = (summary or "").strip() or f"{question} に関する調査結果を整理しました。"
    if normalized_references:
        citation_tokens = " ".join(f"[S{idx}]" for idx, _ in enumerate(normalized_references, start=1))
        if not any(f"[S{idx}]" in summary_text for idx, _ in enumerate(normalized_references, start=1)):
            summary_text = f"{summary_text} {citation_tokens}".strip()
    else:
        summary_text = f"{summary_text} 未確認のため断定は避けます。".strip()
    evidence_json = normalized_evidence_json if evidence is not None else normalized_references
    chunks_for_llm_input = normalized_chunks
    refs_for_llm_input = normalized_references

    llm_settings = _resolve_answer_llm_settings()
    llm_endpoint = str(llm_settings.get("endpoint") or "").strip()
    llm_model = str(llm_settings.get("model") or "local-llm").strip() or "local-llm"
    model_ctx = _first_positive_int(
        _fetch_context_tokens_from_models_api(llm_endpoint, llm_model),
        (llm_settings.get("search_assignment") or {}).get("ctx_size")
        if isinstance(llm_settings.get("search_assignment"), dict)
        else None,
        os.environ.get("NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS", "").strip(),
        os.environ.get("DEFAULT_LLM_CTX_SIZE", "").strip(),
        16384,
    ) or 16384
    preferred_profile = choose_profile_name(model_ctx)

    instruction_tokens_estimate = estimate_tokens(
        "あなたは調査回答アシスタントです。必ず根拠に基づいて日本語で回答してください。"
        "Evidence 以外を根拠に断定しないこと。"
        "重要主張ごとに [S1] 形式のcitationを必ず付与すること。"
    )
    question_tokens_estimate = estimate_tokens(question)
    source_metadata_tokens_estimate = estimate_tokens(
        "\n".join(
            f"{ref.get('citation_label', '')} {ref.get('title', '')} {ref.get('url', '')}"
            for ref in normalized_references[:120]
        )
    )
    context_budget = build_context_budget(
        max_context_tokens=model_ctx,
        instruction_tokens_estimate=instruction_tokens_estimate,
        question_tokens_estimate=question_tokens_estimate,
        source_metadata_tokens_estimate=source_metadata_tokens_estimate,
        preferred_profile=preferred_profile,
    )
    compressed = compress_global_evidence(
        question,
        refs_for_llm_input,
        chunks_for_llm_input,
        context_budget,
    )
    refs_for_llm = compressed["references"]
    chunks_for_llm = compressed["chunks"]
    compression_stats = dict(compressed["stats"])
    estimated_prompt_tokens = estimate_tokens(
        question
        + "\\n"
        + "\\n".join(str(chunk.get("quote") or chunk.get("text") or "") for chunk in chunks_for_llm)
        + "\\n"
        + "\\n".join(str(ref.get("title") or "") for ref in refs_for_llm)
    )

    llm_answer: str | None = None
    generation_mode = "template_fallback"
    llm_enabled = bool(llm_settings.get("enabled"))
    llm_reachable = bool(llm_settings.get("reachable"))
    llm_model_role = str(llm_settings.get("model_role") or "SEARCH")
    llm_model_source = str(llm_settings.get("model_source") or "fallback")
    llm_probe_error = str(llm_settings.get("probe_error") or "").strip()
    llm_selected_reason = str(llm_settings.get("selected_reason") or "").strip()
    llm_probe_status = llm_settings.get("probe_status") if isinstance(llm_settings.get("probe_status"), list) else []
    llm_error: str | None = None
    retry_count = 0
    retry_applied_profile = ""
    if chunks_for_llm:
        try:
            llm_answer = _generate_answer_with_llm(
                question=question,
                references=refs_for_llm,
                evidence_chunks=chunks_for_llm,
                llm_settings=llm_settings,
            )
            generation_mode = "llm_answer"
        except Exception as exc:  # noqa: BLE001
            llm_answer = None
            generation_mode = "template_fallback"
            llm_error = str(exc)
            if _looks_like_context_overflow_error(llm_error):
                retry_count = 1
                retry_profile = stronger_profile(context_budget.compression_profile)
                retry_applied_profile = retry_profile
                retry_budget = build_context_budget(
                    max_context_tokens=model_ctx,
                    instruction_tokens_estimate=instruction_tokens_estimate,
                    question_tokens_estimate=question_tokens_estimate,
                    source_metadata_tokens_estimate=source_metadata_tokens_estimate,
                    preferred_profile=retry_profile,
                )
                retry_compressed = compress_global_evidence(
                    question,
                    refs_for_llm_input,
                    chunks_for_llm_input,
                    retry_budget,
                )
                retry_refs = retry_compressed["references"]
                retry_chunks = retry_compressed["chunks"]
                try:
                    llm_answer = _generate_answer_with_llm(
                        question=question,
                        references=retry_refs,
                        evidence_chunks=retry_chunks,
                        llm_settings=llm_settings,
                    )
                    generation_mode = "llm_answer"
                    llm_error = None
                    context_budget = retry_budget
                    refs_for_llm = retry_refs
                    chunks_for_llm = retry_chunks
                    compression_stats = dict(retry_compressed["stats"])
                    estimated_prompt_tokens = estimate_tokens(
                        question
                        + "\\n"
                        + "\\n".join(str(chunk.get("quote") or chunk.get("text") or "") for chunk in chunks_for_llm)
                    )
                except Exception as retry_exc:  # noqa: BLE001
                    llm_answer = None
                    llm_error = str(retry_exc)
                    generation_mode = "template_fallback"

    final_summary = replace_citation_labels(llm_answer or summary_text, normalized["label_map"])

    answer_markdown = _build_answer_markdown(
        question=question,
        summary=final_summary,
        references=normalized_references,
    )
    citation_verification = verify_citation_labels(
        answer_text=final_summary,
        references=normalized_references,
        evidence_chunks=normalized_chunks,
        verifier=citation_support_verifier,
    )

    generation = {
        "mode": generation_mode,
        "llm_enabled": llm_enabled,
        "llm_endpoint": llm_endpoint,
        "llm_model": llm_model,
        "model_role": llm_model_role,
        "model_source": llm_model_source,
        "llm_reachable": llm_reachable,
        "probe_error": llm_probe_error,
        "selected_reason": llm_selected_reason,
        "probe_status": llm_probe_status,
        "max_context_tokens": context_budget.max_context_tokens,
        "compression_profile": context_budget.compression_profile,
        "auto_budget": context_budget.auto_budget,
        "evidence_budget_tokens": context_budget.max_evidence_tokens,
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "compression": compression_stats,
        "retry_count": retry_count,
        "retry_profile": retry_applied_profile,
        "context_budget": {
            "max_context_tokens": context_budget.max_context_tokens,
            "reserved_output_tokens": context_budget.reserved_output_tokens,
            "safety_tokens": context_budget.safety_tokens,
            "max_evidence_tokens": context_budget.max_evidence_tokens,
        },
        "error": llm_error,
        "notice": (
            "Answer LLM is disabled. Deep Research generated a template fallback answer."
            if not llm_enabled
            else (
                "Answer LLM endpoint is unreachable. Deep Research generated a template fallback answer."
                if not llm_reachable
                else (
                    (
                        "Answer LLM request exceeded context size. Evidence was compressed and retried, but generation still failed."
                        if llm_error and retry_count > 0 and _looks_like_context_overflow_error(llm_error)
                        else "Answer LLM request failed. Deep Research generated a template fallback answer."
                    )
                    if llm_error
                    else (
                        ("Evidence was compressed to fit the model context." if retry_count > 0 else "")
                        if chunks_for_llm
                        else "No evidence chunks were available. Deep Research generated a template fallback answer."
                    )
                )
            )
        ),
    }

    payload = {
        "question": question,
        "answer": final_summary,
        "answer_markdown": answer_markdown,
        "evidence_json": evidence_json,
        "references": normalized_references,
        "citation_verification": citation_verification,
        "generation": generation,
        # Backward compatibility: duplicated top-level keys during migration window.
        "generation_mode": generation_mode,
        "llm_enabled": llm_enabled,
        "llm_endpoint": llm_endpoint,
        "llm_model": llm_model,
        "llm_reachable": llm_reachable,
        "model_role": llm_model_role,
        "model_source": llm_model_source,
        "probe_error": llm_probe_error,
        "selected_reason": llm_selected_reason,
        "probe_status": llm_probe_status,
        "llm_error": llm_error,
    }

    if job_id:
        paths = _write_answer_files(job_id=job_id, answer_markdown=answer_markdown, answer_json=payload)
        answer_id = _save_answer_row(
            job_id=job_id,
            project=project,
            question=question,
            answer_markdown=answer_markdown,
            evidence_json=evidence_json,
            references=normalized_references,
            answer_payload=payload,
        )
        payload.update(paths)
        payload["answer_id"] = answer_id

    return payload
