from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib import error, request
import uuid

from app.nexus.config import NEXUS_PATHS
from app.nexus.db import transaction
from app.nexus.utils import ensure_dir


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
    value = str(os.environ.get("NEXUS_ENABLE_ANSWER_LLM", "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _generate_answer_with_llm(
    *,
    question: str,
    references: list[dict],
    evidence_chunks: list[dict],
    timeout_sec: float | None = None,
) -> str:
    if not _llm_answer_enabled():
        raise RuntimeError("answer llm is disabled")

    endpoint = str(os.environ.get("NEXUS_ANSWER_LLM_ENDPOINT", "http://127.0.0.1:8000/v1/chat/completions")).strip()
    model = str(os.environ.get("NEXUS_ANSWER_LLM_MODEL", "local-llm")).strip() or "local-llm"
    timeout_value = float(timeout_sec or os.environ.get("NEXUS_ANSWER_LLM_TIMEOUT_SEC", "20"))

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
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req, timeout=timeout_value) as resp:
            raw = resp.read().decode("utf-8")
    except TimeoutError as exc:
        raise TimeoutError("answer llm timeout") from exc
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
                answer_markdown, evidence_json, source_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                job_id,
                project,
                question,
                answer_markdown,
                json.dumps(evidence_json, ensure_ascii=False),
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
) -> dict:
    summary_text = (summary or "").strip() or f"{question} に関する調査結果を整理しました。"
    if references:
        citation_tokens = " ".join(f"[S{idx}]" for idx, _ in enumerate(references, start=1))
        if not any(f"[S{idx}]" in summary_text for idx, _ in enumerate(references, start=1)):
            summary_text = f"{summary_text} {citation_tokens}".strip()
    else:
        summary_text = f"{summary_text} 未確認のため断定は避けます。".strip()
    evidence_json = evidence if evidence is not None else references
    chunks_for_llm = evidence_chunks if evidence_chunks is not None else []

    llm_answer: str | None = None
    if chunks_for_llm:
        try:
            llm_answer = _generate_answer_with_llm(
                question=question,
                references=references,
                evidence_chunks=chunks_for_llm,
            )
        except Exception:  # noqa: BLE001
            llm_answer = None

    final_summary = llm_answer or summary_text

    answer_markdown = _build_answer_markdown(
        question=question,
        summary=final_summary,
        references=references,
    )
    payload = {
        "question": question,
        "answer": final_summary,
        "answer_markdown": answer_markdown,
        "evidence_json": evidence_json,
        "references": references,
    }

    if job_id:
        paths = _write_answer_files(job_id=job_id, answer_markdown=answer_markdown, answer_json=payload)
        answer_id = _save_answer_row(
            job_id=job_id,
            project=project,
            question=question,
            answer_markdown=answer_markdown,
            evidence_json=evidence_json,
            references=references,
        )
        payload.update(paths)
        payload["answer_id"] = answer_id

    return payload
