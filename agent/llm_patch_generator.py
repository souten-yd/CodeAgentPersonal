from __future__ import annotations

import difflib
import json
from pathlib import Path
from uuid import uuid4

from agent.patch_schema import PatchProposal

MAX_PROMPT_CONTENT_CHARS = 12_000
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


def _build_content_excerpt(content: str) -> str:
    if len(content) <= MAX_PROMPT_CONTENT_CHARS:
        return content
    head = content[: MAX_PROMPT_CONTENT_CHARS // 2]
    tail = content[-MAX_PROMPT_CONTENT_CHARS // 2 :]
    return f"{head}\n\n...<omitted>...\n\n{tail}"


def _build_prompt(target_file: Path, step_title: str, step_description: str, file_content: str) -> str:
    excerpt = _build_content_excerpt(file_content)
    return (
        "Return JSON only.\n"
        "Keys: original_block, replacement_block, rationale, risk_notes.\n"
        "If unsure, return {}.\n"
        "Single file only.\n"
        "original_block must be exact text from the file and uniquely matched.\n"
        "replacement_block must be a small edit from original_block.\n"
        "No full file replacement.\n"
        "No dependency/config/secret changes.\n"
        "No shell commands.\n"
        "changed lines <= 120.\n"
        f"Target file: {target_file.name}\n"
        f"Step: {step_title}\n"
        f"Description: {step_description}\n"
        "FILE CONTENT:\n"
        f"{excerpt}"
    )


def generate_replace_block_patch(
    run_id: str,
    plan_id: str,
    step_id: str,
    step_title: str,
    step_description: str,
    risk_level: str,
    target_file: Path,
    file_content: str,
    llm_fn=None,
    context: dict | None = None,
) -> PatchProposal:
    patch_id = f"patch_{uuid4().hex[:12]}"
    prompt = _build_prompt(target_file, step_title, step_description, file_content)
    metadata = {"context": context or {}}

    def invalid(reason: str, warnings: list[str], raw: str = "", sanitized: bool = False, original: str = "", replacement: str = "") -> PatchProposal:
        return PatchProposal(
            patch_id=patch_id,
            run_id=run_id,
            plan_id=plan_id,
            step_id=step_id,
            target_file=str(target_file),
            patch_type="replace_block",
            risk_level=risk_level,
            apply_allowed=False,
            can_apply_reason=reason,
            generator="llm_replace_block",
            llm_prompt_preview=prompt[:500],
            llm_raw_output_preview=(raw or "")[:1000],
            llm_sanitized=sanitized,
            safety_warnings=warnings,
            original_block=original,
            replacement_block=replacement,
            metadata=metadata,
        )

    if llm_fn is None:
        return invalid("llm_unavailable", ["llm_fn is None"])
    try:
        raw = str(llm_fn(prompt=prompt, target_file=str(target_file), content=file_content) or "")
    except Exception as exc:
        return invalid("llm_error", [f"llm_error: {exc}"], raw="", sanitized=False)

    json_text, sanitized = _extract_json_text(raw)
    try:
        payload = json.loads(json_text)
    except Exception:
        return invalid("invalid_json", ["LLM output is not valid JSON object"], raw=raw, sanitized=sanitized)
    if not isinstance(payload, dict):
        return invalid("invalid_json_type", ["LLM output JSON must be object"], raw=raw, sanitized=sanitized)

    original = payload.get("original_block", "")
    replacement = payload.get("replacement_block", "")
    if not isinstance(original, str) or not isinstance(replacement, str):
        return invalid("invalid_block_type", ["original_block/replacement_block must be strings"], raw=raw, sanitized=sanitized)
    if not original:
        return invalid("empty_original_block", ["original_block is empty"], raw=raw, sanitized=sanitized)
    if not replacement:
        return invalid("empty_replacement_block", ["replacement_block is empty"], raw=raw, sanitized=sanitized, original=original)
    if original == replacement:
        return invalid("same_original_replacement", ["original_block equals replacement_block"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    match_count = file_content.count(original)
    if match_count == 0:
        return invalid("original_block_no_match", ["original_block not found in file"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)
    if match_count > 1:
        return invalid("original_block_multiple_match", ["original_block is ambiguous"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    if len(replacement.encode("utf-8")) > MAX_REPLACEMENT_BYTES:
        return invalid("replacement_too_large", ["replacement block too large"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)
    total_lines = max(1, len(file_content.splitlines()))
    original_lines = len(original.splitlines())
    if original_lines > max(3, int(total_lines * 0.5)):
        return invalid("replacement_scope_too_large", ["original block scope exceeds 50% of file"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    lowered = replacement.lower()
    if any(x in lowered for x in ["password", "token", "secret", "api_key"]):
        return invalid("sensitive_pattern_detected", ["replacement may include sensitive token"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)
    if any(x in lowered for x in ["rm -rf", "os.system", "subprocess", "eval(", "exec("]):
        return invalid("dangerous_pattern_detected", ["dangerous pattern detected"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    new_content = file_content.replace(original, replacement, 1)
    diff = "\n".join(difflib.unified_diff(file_content.splitlines(), new_content.splitlines(), fromfile=str(target_file), tofile=str(target_file), lineterm=""))
    if not diff.strip():
        return invalid("empty_unified_diff", ["unified diff is empty"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)
    changed_lines = sum(1 for line in diff.splitlines() if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")))
    if changed_lines > MAX_CHANGED_LINES:
        return invalid("changed_lines_exceeds_limit", ["changed lines exceeds limit"], raw=raw, sanitized=sanitized, original=original, replacement=replacement)

    return PatchProposal(
        patch_id=patch_id,
        run_id=run_id,
        plan_id=plan_id,
        step_id=step_id,
        target_file=str(target_file),
        patch_type="replace_block",
        risk_level=risk_level,
        original_preview=file_content[:400],
        proposed_content="",
        unified_diff=diff,
        original_block=original,
        replacement_block=replacement,
        match_strategy="exact",
        match_count=match_count,
        can_apply_reason="exact_match",
        generator="llm_replace_block",
        llm_prompt_preview=prompt[:500],
        llm_raw_output_preview=raw[:1000],
        llm_sanitized=sanitized,
        apply_allowed=True,
        metadata=metadata,
    )
