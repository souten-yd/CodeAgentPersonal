from __future__ import annotations

import difflib
import json
from pathlib import Path
from uuid import uuid4

from agent.patch_schema import PatchProposal


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
        txt = txt[start:end+1]
    return txt, sanitized


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
    prompt = f"""Return JSON only with keys original_block, replacement_block, rationale, risk_notes.\nTarget file: {target_file.name}\nStep: {step_title}\nDescription: {step_description}\n"""
    metadata = {"context": context or {}}
    if llm_fn is None:
        return PatchProposal(
            patch_id=patch_id, run_id=run_id, plan_id=plan_id, step_id=step_id,
            target_file=str(target_file), patch_type="replace_block", risk_level=risk_level,
            apply_allowed=False, can_apply_reason="llm_unavailable", generator="llm_replace_block",
            llm_prompt_preview=prompt[:500], metadata={**metadata, "llm_warning": "llm_fn is None"},
        )
    try:
        raw = str(llm_fn(prompt=prompt, target_file=str(target_file), content=file_content) or "")
    except Exception as exc:
        return PatchProposal(
            patch_id=patch_id, run_id=run_id, plan_id=plan_id, step_id=step_id,
            target_file=str(target_file), patch_type="replace_block", risk_level=risk_level,
            apply_allowed=False, can_apply_reason="llm_error", generator="llm_replace_block",
            llm_prompt_preview=prompt[:500], metadata={**metadata, "llm_error": str(exc)},
        )

    json_text, sanitized = _extract_json_text(raw)
    try:
        payload = json.loads(json_text)
    except Exception:
        payload = {}

    original = str(payload.get("original_block", ""))
    replacement = str(payload.get("replacement_block", ""))
    match_count = file_content.count(original) if original else 0
    can_apply = bool(original and replacement and match_count == 1)
    reason = "exact_match" if can_apply else "invalid_or_ambiguous_match"
    new_content = file_content.replace(original, replacement, 1) if can_apply else file_content
    diff = "\n".join(difflib.unified_diff(file_content.splitlines(), new_content.splitlines(), fromfile=str(target_file), tofile=str(target_file), lineterm=""))
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
        match_strategy="exact" if original else "unavailable",
        match_count=match_count,
        can_apply_reason=reason,
        generator="llm_replace_block",
        llm_prompt_preview=prompt[:500],
        llm_raw_output_preview=raw[:1000],
        llm_sanitized=sanitized,
        apply_allowed=can_apply,
        metadata=metadata,
    )
