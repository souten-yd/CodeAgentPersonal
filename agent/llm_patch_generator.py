from __future__ import annotations

import difflib
import json
from pathlib import Path
from uuid import uuid4

from agent.patch_context_selector import PatchContextSelector
from agent.patch_quality import PatchQualityEvaluator
from agent.patch_schema import PatchProposal

MAX_REPLACEMENT_BYTES = 20_000
MAX_CHANGED_LINES = 120


def _extract_json_text(raw: str) -> tuple[str, bool]:
    txt = (raw or "").strip()
    sanitized = False
    if txt.startswith("```"):
        sanitized = True
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    start = txt.find("{")
    end = txt.rfind("}")
    if start != -1 and end > start:
        if start != 0 or end != len(txt) - 1:
            sanitized = True
        txt = txt[start:end + 1]
    return txt, sanitized


def _build_prompt(target_file: Path, step_title: str, step_description: str, candidates: list) -> str:
    cand_text = []
    for c in candidates:
        cand_text.append(f"[{c.candidate_id}] lines {c.start_line}-{c.end_line} reason={c.reason}\n{c.text}")
    return (
        "Return JSON only.\n"
        "Keys: candidate_id, original_block, replacement_block, rationale, risk_notes, confidence.\n"
        "If unsure, return {}.\n"
        "candidate_id must be one of provided candidates.\n"
        "original_block must be exact text from candidate/file and uniquely matched.\n"
        "replacement_block must be a small edit.\n"
        "No full file replacement. No dependency/config/secret changes.\n"
        "No shell commands. changed lines <= 120.\n"
        f"Target file: {target_file.name}\nStep: {step_title}\nDescription: {step_description}\n"
        "CANDIDATE BLOCKS:\n" + "\n\n".join(cand_text)
    )


def generate_replace_block_patch(run_id: str, plan_id: str, step_id: str, step_title: str, step_description: str, risk_level: str, target_file: Path, file_content: str, llm_fn=None, context: dict | None = None) -> PatchProposal:
    patch_id = f"patch_{uuid4().hex[:12]}"
    selector = PatchContextSelector()
    candidates = selector.select_candidates(file_content, step_title, step_description, max_candidates=5, target_file=str(target_file))
    prompt = _build_prompt(target_file, step_title, step_description, candidates)
    metadata = {"context": context or {}, "candidates_summary": [{"candidate_id": c.candidate_id, "reason": c.reason, "start_line": c.start_line, "end_line": c.end_line} for c in candidates], "prompt_chars": len(prompt)}

    def finalize(p: PatchProposal) -> PatchProposal:
        q = PatchQualityEvaluator().evaluate(p, file_content, step_title, step_description)
        p.quality_score = q.quality_score
        p.quality_warnings = q.warnings
        p.quality_summary = q.summary
        p.candidate_block_count = len(candidates)
        if not p.selected_candidate_reason:
            p.selected_candidate_reason = ""
        return p

    def invalid(reason: str, warnings: list[str], raw: str = "", sanitized: bool = False, original: str = "", replacement: str = "") -> PatchProposal:
        md = {**metadata, "raw_output_chars": len(raw or ""), "validation_reason": reason}
        return finalize(PatchProposal(patch_id=patch_id, run_id=run_id, plan_id=plan_id, step_id=step_id, target_file=str(target_file), patch_type="replace_block", risk_level=risk_level, apply_allowed=False, can_apply_reason=reason, generator="llm_replace_block", llm_prompt_preview=prompt[:500], llm_raw_output_preview=(raw or "")[:1000], llm_sanitized=sanitized, safety_warnings=warnings, original_block=original, replacement_block=replacement, metadata=md, candidate_block_count=len(candidates)))

    if llm_fn is None:
        return invalid("llm_unavailable", ["llm_fn is None"])
    try:
        raw = str(llm_fn(prompt=prompt, target_file=str(target_file), content=file_content) or "")
    except Exception as exc:
        md = {**metadata, "llm_error": str(exc)}
        return finalize(PatchProposal(patch_id=patch_id, run_id=run_id, plan_id=plan_id, step_id=step_id, target_file=str(target_file), patch_type="replace_block", risk_level=risk_level, apply_allowed=False, can_apply_reason="llm_error", generator="llm_replace_block", llm_prompt_preview=prompt[:500], llm_raw_output_preview="", llm_sanitized=False, safety_warnings=[f"llm_error: {exc}"], metadata=md, candidate_block_count=len(candidates)))

    json_text, sanitized = _extract_json_text(raw)
    try:
        payload = json.loads(json_text)
    except Exception:
        return invalid("invalid_json", ["LLM output is not valid JSON object"], raw=raw, sanitized=sanitized)
    if not isinstance(payload, dict):
        return invalid("invalid_json_type", ["LLM output JSON must be object"], raw=raw, sanitized=sanitized)

    candidate_id = str(payload.get("candidate_id", "") or "")
    original = payload.get("original_block", "")
    replacement = payload.get("replacement_block", "")
    metadata["candidate_id"] = candidate_id
    metadata["llm_confidence"] = payload.get("confidence", 0.0)
    selected = next((c for c in candidates if c.candidate_id == candidate_id), None)
    selected_reason = selected.reason if selected else ""

    if not isinstance(original, str) or not isinstance(replacement, str):
        return invalid("invalid_block_type", ["original_block/replacement_block must be strings"], raw=raw, sanitized=sanitized)
    if not original:
        return invalid("empty_original_block", ["original_block is empty"], raw=raw, sanitized=sanitized)
    if not replacement:
        return invalid("empty_replacement_block", ["replacement_block is empty"], raw=raw, sanitized=sanitized, original=original)

    match_count = file_content.count(original)
    if match_count != 1:
        return invalid("original_block_match_error", ["original_block must match exactly once"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)
    if len(replacement.encode("utf-8")) > MAX_REPLACEMENT_BYTES:
        return invalid("replacement_too_large", ["replacement block too large"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    new_content = file_content.replace(original, replacement, 1)
    diff = "\n".join(difflib.unified_diff(file_content.splitlines(), new_content.splitlines(), fromfile=str(target_file), tofile=str(target_file), lineterm=""))
    changed_lines = sum(1 for line in diff.splitlines() if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")))
    if changed_lines > MAX_CHANGED_LINES:
        return invalid("changed_lines_exceeds_limit", ["changed lines exceeds limit"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    metadata["raw_output_chars"] = len(raw or "")
    metadata["validation_reason"] = "exact_match"
    return finalize(PatchProposal(patch_id=patch_id, run_id=run_id, plan_id=plan_id, step_id=step_id, target_file=str(target_file), patch_type="replace_block", risk_level=risk_level, original_preview=file_content[:400], proposed_content="", unified_diff=diff, original_block=original, replacement_block=replacement, match_strategy="exact", match_count=1, can_apply_reason="exact_match", generator="llm_replace_block", llm_prompt_preview=prompt[:500], llm_raw_output_preview=raw[:1000], llm_sanitized=sanitized, apply_allowed=True, metadata=metadata, candidate_block_count=len(candidates), selected_candidate_reason=selected_reason))
