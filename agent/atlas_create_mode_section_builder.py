"""Create-mode within-file section builder (the "create-mode span bridge").

A weak local model can hit an algorithmic ceiling generating a complex file (e.g. a raycasting
renderer) in ONE call and return no content, even when the file is already small and focused.
Retrying the whole-file generation cannot help — the per-call complexity is the ceiling.

This module lowers per-call complexity for a CREATE by turning ONE hard generation into:
  1. a small **skeleton** call — a lightweight, single-file "fast plan": the module/class
     declarations, ALL shared state/fields, and method signatures, with each real body replaced by a
     single deterministic marker line ``// __SECTION__: <name>``; then
  2. one small **section** call per marker that returns ONLY that body; spliced deterministically
     back into the skeleton by exact marker match.

Determinism lives here (marker enumeration + splice + assembly); only the two small prompt shapes go
to the model. Intra-file consistency comes from the skeleton being the single source of truth for the
file's shape (every section fill sees the whole skeleton); cross-file consistency is the caller's job
(it passes the already-built shared-resource / interface contracts + sibling files, unchanged).

Bounded by design: capped section count + per-section retries; a section that stays empty ends the
build as ``capability_ceiling`` (naming the section) rather than looping. NO apply/IO happens here.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from agent.atlas_llm_json_adapter import call_llm_json

# One body line, on its own, marks a section the skeleton deferred to a focused fill call.
SECTION_MARKER_RE = re.compile(
    r"^(?P<indent>[ \t]*)//\s*__SECTION__:\s*(?P<name>[A-Za-z0-9_]+)\s*$", re.MULTILINE
)

_SKELETON_MAX_TOKENS = 1500
_SECTION_MAX_TOKENS = 1400
_MAX_SECTIONS = 20
_SECTION_RETRIES = 2
_SKELETON_RETRIES = 3

# Declaration lines that define a sibling's cross-file API (classes/functions/exported globals).
# The skeleton + section fills only need these to stay consistent — NOT each sibling's full body,
# which for an integration file (many siblings) blows the context window and makes a weak model
# return an empty completion.
_SIGNATURE_RE = re.compile(
    r"^\s*(?:export\s+)?(?:class\s+\w+|(?:async\s+)?function\s+\w+|const\s+[A-Z]\w*\s*=|"
    r"(?:window|globalThis)\.\w+\s*=|[A-Za-z_]\w*\s*\([^)]*\)\s*\{)",
)

_SKELETON_SCHEMA = {
    "type": "object",
    "properties": {"proposed_content": {"type": "string"}},
    "required": ["proposed_content"],
    "additionalProperties": True,
}
_SECTION_SCHEMA = {
    "type": "object",
    "properties": {"body": {"type": "string"}},
    "required": ["body"],
    "additionalProperties": True,
}

_SYSTEM = "You are a precise, terse code generator. Return JSON only, no prose."


def enumerate_sections(skeleton: str) -> list[dict]:
    """Ordered, de-duplicated section markers found in the skeleton."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in SECTION_MARKER_RE.finditer(skeleton or ""):
        name = m.group("name")
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "indent": m.group("indent") or ""})
    return out


def splice_section(text: str, name: str, body: str, indent: str) -> tuple[str, bool]:
    """Replace the ``// __SECTION__: <name>`` marker line with an indented body. Returns
    (new_text, replaced)."""
    marker_re = re.compile(
        r"^[ \t]*//\s*__SECTION__:\s*" + re.escape(name) + r"\s*$", re.MULTILINE
    )
    m = marker_re.search(text)
    if not m:
        return text, False
    raw_lines = _strip_code_fence(body).strip("\n").splitlines() or [""]
    indented = "\n".join((indent + ln) if ln.strip() else ln for ln in raw_lines)
    return text[: m.start()] + indented + text[m.end():], True


def _strip_code_fence(body: str) -> str:
    b = str(body or "").strip()
    if b.startswith("```"):
        b = re.sub(r"^```[a-zA-Z0-9_]*\n?", "", b)
        b = re.sub(r"\n?```$", "", b)
    return b


def body_is_placeholder(body: str) -> bool:
    """True when a section body carries no real implementation (empty, or only comments / the marker /
    a bare `pass`/`...`/`return`)."""
    b = _strip_code_fence(body).strip()
    if not b:
        return True
    if SECTION_MARKER_RE.search(b):
        return True
    # only comments / whitespace
    if re.fullmatch(r"(?:\s*(?://[^\n]*|/\*.*?\*/)\s*)+", b, re.DOTALL):
        return True
    if b in {"pass", "...", "return", "return;", "{}", "return null;", "return undefined;"}:
        return True
    return False


def _sibling_digest(sibling_files: dict[str, Any] | None, *, per_file_chars: int = 1800, max_files: int = 6) -> str:
    """Compact read-only context: each sibling file's path + a capped slice of its content so the
    section fills honour the real cross-file API without blowing the context window."""
    lines: list[str] = []
    for i, (path, entry) in enumerate((sibling_files or {}).items()):
        if i >= max_files:
            break
        content = entry.get("content") if isinstance(entry, dict) else entry
        content = str(content or "")
        if not content.strip():
            continue
        lines.append(f"--- {path} ---\n{content[:per_file_chars]}")
    return "\n\n".join(lines)


def _sibling_signatures(sibling_files: dict[str, Any] | None, *, max_lines_per_file: int = 40, max_files: int = 12) -> str:
    """Compact cross-file API view: each sibling's class/function/global DECLARATION lines only (not
    bodies). Small enough that an integration file with many siblings still fits the context window,
    while keeping every symbol the new file must call by its exact name."""
    out: list[str] = []
    for i, (path, entry) in enumerate((sibling_files or {}).items()):
        if i >= max_files:
            break
        content = entry.get("content") if isinstance(entry, dict) else entry
        content = str(content or "")
        if not content.strip():
            continue
        sigs = [ln.strip() for ln in content.splitlines() if _SIGNATURE_RE.match(ln)]
        if not sigs:
            continue
        out.append(f"--- {path} (API) ---\n" + "\n".join(sigs[:max_lines_per_file]))
    return "\n\n".join(out)


def build_file_by_sections(
    *,
    llm_json_fn: Callable[..., Any],
    target_path: str,
    item: dict,
    sibling_files: dict[str, Any] | None = None,
    resource_contract: dict | None = None,
    interface_contract: dict | None = None,
    research_brief: str = "",
    max_sections: int = _MAX_SECTIONS,
    section_retries: int = _SECTION_RETRIES,
) -> dict:
    """Build one file via skeleton + per-section fill. Returns a dict:
    {status: "ok"|"capability_ceiling"|"no_content", proposed_content, sections_done,
     sections_failed, warnings}. Never raises for model behaviour; only bounded LLM calls."""
    warnings: list[str] = []
    goal = " ".join(
        str(item.get(k) or "")
        for k in ("title", "description", "goal")
    ).strip()
    acceptance = [str(c) for c in (item.get("acceptance_criteria") or []) if str(c).strip()]
    # Skeleton context = sibling API SIGNATURES only (small) so an integration file with many
    # siblings still fits n_ctx; section fills get a bit more (signatures + short body excerpts).
    sibling_api = _sibling_signatures(sibling_files)
    sibling_digest = sibling_api or _sibling_digest(sibling_files, per_file_chars=900, max_files=8)

    # ── 1. Skeleton (the lightweight per-file fast plan) — bounded retries for weak-model variance ──
    skeleton_user = {
        "instruction": (
            "Produce the COMPLETE structure of the single file below as JSON "
            '{"proposed_content": "<file text>"}. Declare the module/classes, ALL shared '
            "state/fields, imports, and every method/function SIGNATURE. For each function body that "
            "needs real logic, put EXACTLY ONE line as its entire body: `// __SECTION__: <name>` "
            "(a unique snake_case name). Do NOT implement those bodies now. Trivial one-liners "
            "(getters, simple assignments) may be written inline. Keep it small and syntactically "
            "valid. Match the cross-file API in shared_resource_contract / interface_contract and the "
            "sibling_api EXACTLY (same DOM ids, globals, function names, render model)."
        ),
        "target_file": target_path,
        "goal": goal,
        "acceptance_criteria": acceptance,
        "shared_resource_contract": resource_contract or {},
        "interface_contract": interface_contract or {},
        "sibling_api": sibling_api,
        "approach_reference": (research_brief or "")[:2000],
    }
    skeleton = ""
    for _sk_attempt in range(1, _SKELETON_RETRIES + 1):
        skel_out = _call(llm_json_fn, skeleton_user, _SKELETON_SCHEMA, _SKELETON_MAX_TOKENS)
        skeleton = _strip_code_fence(str((skel_out or {}).get("proposed_content") or ""))
        if skeleton.strip():
            break
    if not skeleton.strip():
        return {
            "status": "no_content", "reason": "skeleton_no_content",
            "proposed_content": "", "sections_done": [], "sections_failed": [],
            "warnings": ["create_mode_section_skeleton_no_content"],
        }

    sections = enumerate_sections(skeleton)
    if not sections:
        # The skeleton is already a complete small file (no deferred bodies) — accept it as-is.
        warnings.append("create_mode_section_skeleton_complete_no_sections")
        return {
            "status": "ok", "proposed_content": skeleton,
            "sections_done": [], "sections_failed": [], "warnings": warnings,
        }

    # ── 2. Per-section fills, spliced deterministically ─────────────────────────────────
    text = skeleton
    done: list[str] = []
    failed: list[str] = []
    for section in sections[:max_sections]:
        name = section["name"]
        body = ""
        for _attempt in range(1, section_retries + 1):
            section_user = {
                "instruction": (
                    f"Implement ONLY the body of the section named '{name}' for the file below. "
                    'Return JSON {"body": "<statements>"} — ONLY the statements that replace the '
                    "`// __SECTION__: " + name + "` line, NOT the whole function, NOT the whole file, "
                    "no signature, no surrounding braces. Use the skeleton's declared fields/methods "
                    "and the siblings; match their names exactly. Write real, complete logic."
                ),
                "section_name": name,
                "target_file": target_path,
                "goal": goal,
                "file_skeleton": text[:9000],
                "shared_resource_contract": resource_contract or {},
                "sibling_files": sibling_digest,
                "approach_reference": (research_brief or "")[:2000],
            }
            sec_out = _call(llm_json_fn, section_user, _SECTION_SCHEMA, _SECTION_MAX_TOKENS)
            body = str((sec_out or {}).get("body") or "")
            if not body_is_placeholder(body):
                break
        if body_is_placeholder(body):
            failed.append(name)
            continue
        spliced, ok = splice_section(text, name, body, section["indent"])
        if ok:
            text = spliced
            done.append(name)
        else:
            failed.append(name)

    remaining = [s["name"] for s in enumerate_sections(text)]
    unresolved = failed + [r for r in remaining if r not in failed]
    if unresolved:
        return {
            "status": "capability_ceiling",
            "proposed_content": text,
            "sections_done": done,
            "sections_failed": unresolved,
            "warnings": warnings + [f"create_mode_section_ceiling:{','.join(unresolved)}"],
        }
    return {
        "status": "ok",
        "proposed_content": text,
        "sections_done": done,
        "sections_failed": [],
        "warnings": warnings + ["create_mode_section_recovery_applied"],
    }


def _call(llm_json_fn: Callable[..., Any], user_obj: dict, schema: dict, max_tokens: int) -> dict:
    try:
        out = call_llm_json(
            llm_json_fn, _SYSTEM, json.dumps(user_obj, ensure_ascii=False),
            json_schema=schema, max_output_tokens=max_tokens,
        )
        return out if isinstance(out, dict) else {}
    except Exception:  # noqa: BLE001 — a failed call is treated as empty; the caller bounds retries.
        return {}
