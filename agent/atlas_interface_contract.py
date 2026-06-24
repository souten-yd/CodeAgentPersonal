"""Shared app interface contract — the integration backbone for a multi-item build.

When a single app (e.g. an HTML5 game) is built across many plan items that each edit the SAME
file, the items must agree on the SAME object model, identifiers and wiring or the result does not
integrate (enemies never spawn because nothing calls enemyManager.spawn(); the player is misplaced
because each item invents its own coordinates). A weak local model cannot infer this agreement on
its own.

This module asks the model ONCE, up front, to define a concrete shared interface contract — the
entities, their public API/properties, the shared state, and how the main loop wires them — which
is then injected into EVERY item's generation prompt so each step implements/consumes the SAME
interface. It complements the greenfield/digital-twin Blueprint `interfaces` (same intent), but is
produced at plan time and travels on the pool so it is available to every generation flow.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from agent.atlas_llm_json_adapter import call_llm_json

# An app is "interface-coupled" (worth a shared contract) when several plan items write the SAME
# file(s) — that is exactly when integration drift between items appears.
_MIN_ITEMS_SHARING_A_FILE = 2

_CONTRACT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "shared_state": {"type": "string"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string"},
                    "properties": {"type": "array", "items": {"type": "string"}},
                    "methods": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        "wiring": {"type": "string"},
        "init": {"type": "string"},
    },
    "required": ["entities", "wiring"],
}

_SYSTEM_PROMPT = (
    "You are a software architect. Define the SHARED INTERFACE CONTRACT for a small app that will be "
    "built incrementally by several steps, all editing the same file(s). Return a SINGLE JSON object "
    "only. The contract MUST let independent steps integrate: pick the exact identifiers, each "
    "entity's public methods/properties, the shared state, and how the main loop wires every entity "
    "together. Be concrete and minimal — real names a developer would use, not prose. When CURRENT "
    "FILE CONTENT is provided, EXTRACT the contract from the code that ALREADY exists (reuse its real "
    "names) and only extend it for the planned steps — never rename or contradict existing identifiers."
)


def app_is_interface_coupled(items: list[Any]) -> bool:
    """True when >= _MIN_ITEMS_SHARING_A_FILE plan items target the same file (integration risk)."""
    counts: dict[str, int] = {}
    for it in items or []:
        targets = getattr(it, "target_files", None)
        if targets is None and isinstance(it, dict):
            targets = it.get("target_files")
        for path in (targets or []):
            key = str(path).strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return any(n >= _MIN_ITEMS_SHARING_A_FILE for n in counts.values())


def build_app_interface_contract(
    *,
    goal: str,
    item_titles: list[str],
    target_files: list[str],
    llm_json_fn: Callable[[str, str], dict | None] | None,
    existing_content: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Ask the model for the shared interface contract. Returns the contract dict, or None when the
    model is unavailable / returns nothing usable (the caller then proceeds without a contract).

    For EXISTING code, pass ``existing_content`` (path -> current text): the contract is then
    EXTRACTED from the real code so modifications integrate with what is already there, rather than a
    contract invented from scratch (new files)."""
    if llm_json_fn is None:
        return None
    steps = "\n".join(f"- {t}" for t in item_titles[:20] if str(t).strip())
    files = ", ".join(sorted({str(f).strip() for f in target_files if str(f).strip()})) or "index.html"
    existing_block = ""
    for path, content in (existing_content or {}).items():
        body = str(content or "").strip()
        if body:
            existing_block += f"\n\n--- CURRENT CONTENT of {path} (extract its real interface) ---\n{body[:9000]}"
    user_prompt = (
        f"App goal:\n{goal}\n\n"
        f"Target file(s): {files}\n\n"
        f"The app is built/modified by these steps (each edits the file(s) above):\n{steps}\n\n"
        "Produce the shared interface contract so every step integrates. Return JSON with: "
        "\"entities\" (each {name, kind, properties[], methods[], notes}), \"shared_state\" (the "
        "top-level variables/objects every step shares), \"wiring\" (exactly how the main loop / "
        "init calls each entity so they work together — e.g. the game loop order, who spawns what), "
        "\"init\" (what runs on startup), \"files\". Use EXACT identifiers steps must reuse verbatim."
        + (existing_block or "")
    )
    try:
        result = call_llm_json(llm_json_fn, _SYSTEM_PROMPT, user_prompt, json_schema=_CONTRACT_JSON_SCHEMA)
    except Exception:  # noqa: BLE001 — never break generation because the contract step failed.
        return None
    if not isinstance(result, dict):
        return None
    entities = result.get("entities")
    if not isinstance(entities, list) or not entities:
        return None
    # Keep only the contract-relevant keys (drop any stray fields the model added).
    contract = {
        "summary": str(result.get("summary") or ""),
        "files": [str(f) for f in (result.get("files") or []) if str(f).strip()] or list(target_files),
        "shared_state": str(result.get("shared_state") or ""),
        "entities": [_clean_entity(e) for e in entities if isinstance(e, dict)][:24],
        "wiring": str(result.get("wiring") or ""),
        "init": str(result.get("init") or ""),
    }
    if not contract["entities"] or not (contract["wiring"] or contract["shared_state"]):
        return None
    return contract


def _clean_entity(e: dict) -> dict[str, Any]:
    return {
        "name": str(e.get("name") or "").strip(),
        "kind": str(e.get("kind") or "").strip(),
        "properties": [str(p) for p in (e.get("properties") or []) if str(p).strip()][:16],
        "methods": [str(m) for m in (e.get("methods") or []) if str(m).strip()][:16],
        "notes": str(e.get("notes") or "").strip()[:240],
    }


# ── Shared RESOURCE contract (deterministic) ──────────────────────────────────────────────────
# The entity/wiring contract above is an LLM-defined OBJECT model. It does NOT capture the
# cross-cutting PLATFORM decisions that independently-generated per-file units must also agree on —
# and disagreement there is what silently breaks the app. The live failure: game.js drove #gameCanvas
# as a Three.js WebGL surface while main.js did getContext('2d') on the SAME canvas (a canvas allows
# only ONE context type), so WebGL failed and nothing rendered. That is not an "entity" mismatch; it
# is a shared-RESOURCE mismatch. These facts are extractable DETERMINISTICALLY from the existing HTML
# + JS (no weak model needed), which is both more reliable and cheaper than asking the model.

_CANVAS_ID_RE = re.compile(r"<canvas\b[^>]*\bid\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_ELEM_ID_RE = re.compile(r"\bid\s*=\s*[\"']([A-Za-z_][\w\-]*)[\"']")
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_GETCTX_RE = re.compile(r"getContext\(\s*[\"']([^\"']+)[\"']")
_THREE_RE = re.compile(r"\bnew\s+THREE\.|\bTHREE\.\w+|\bWebGLRenderer\b")
_WIN_GLOBAL_RE = re.compile(r"\bwindow\.([A-Za-z_]\w*)\s*=")
_TOPLEVEL_DECL_RE = re.compile(r"^(?:export\s+)?(?:class|function)\s+([A-Za-z_]\w*)", re.MULTILINE)


def _is_html(path: str) -> bool:
    return str(path).lower().endswith((".html", ".htm"))


def _is_js(path: str) -> bool:
    return str(path).lower().endswith((".js", ".mjs", ".cjs", ".jsx"))


def _dedup(seq: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for s in seq:
        s = str(s).strip()
        if s and s not in seen:
            seen[s] = None
    return list(seen.keys())


def _lib_name(src: str) -> str:
    s = src.lower()
    if "three" in s:
        return "THREE (three.js)"
    base = src.rstrip("/").rsplit("/", 1)[-1] or src
    return base


def build_shared_resource_contract(files: dict[str, str]) -> dict[str, Any]:
    """Deterministically extract the shared PLATFORM/RESOURCE facts that every per-file unit must
    agree on, from the app's existing HTML + JS. Captures: the canvas render model (WebGL/Three.js
    vs 2D) and which canvas owns it, the DOM element ids that actually exist, external libraries
    already loaded, and the global symbols each sibling file exposes. No LLM. Returns {} when there
    is nothing app-shaped to constrain."""
    html = {p: c for p, c in (files or {}).items() if _is_html(p) and str(c).strip()}
    js = {p: c for p, c in (files or {}).items() if _is_js(p) and str(c).strip()}

    canvas_ids: list[str] = []
    dom_ids: list[str] = []
    libs: list[str] = []
    for content in html.values():
        canvas_ids += _CANVAS_ID_RE.findall(content)
        dom_ids += _ELEM_ID_RE.findall(content)
        for src in _SCRIPT_SRC_RE.findall(content):
            if src.startswith("http") or src.startswith("//"):
                libs.append(_lib_name(src))

    uses_webgl = any(_THREE_RE.search(c) for c in js.values())
    ctx_types: set[str] = set()
    for c in js.values():
        for t in _GETCTX_RE.findall(c):
            ctx_types.add(t.lower())
    uses_webgl = uses_webgl or any(t.startswith("webgl") for t in ctx_types)
    uses_2d = "2d" in ctx_types
    if uses_webgl:
        render_model = "webgl"
        render_lib = "three.js" if any(_THREE_RE.search(c) for c in js.values()) else ""
    elif uses_2d:
        render_model = "canvas_2d"
        render_lib = ""
    else:
        render_model, render_lib = "", ""

    globals_by_file: dict[str, list[str]] = {}
    for path, content in js.items():
        names = set(_WIN_GLOBAL_RE.findall(content)) | set(_TOPLEVEL_DECL_RE.findall(content))
        if names:
            globals_by_file[path] = sorted(names)[:16]

    contract = {
        "render_model": render_model,                       # "webgl" | "canvas_2d" | ""
        "render_lib": render_lib,                           # "three.js" | ""
        "primary_canvas": (_dedup(canvas_ids)[0] if canvas_ids else ""),
        "canvas_ids": _dedup(canvas_ids),
        "dom_ids": _dedup(dom_ids),
        "external_libs": _dedup(libs),
        "globals_by_file": globals_by_file,
        # Both a WebGL and a 2D context are requested somewhere → a guaranteed runtime break.
        "context_conflict": bool(uses_webgl and uses_2d),
    }
    if not (contract["primary_canvas"] or contract["dom_ids"] or contract["globals_by_file"]):
        return {}
    return contract


def render_shared_resource_contract_for_prompt(contract: dict[str, Any]) -> str:
    """Imperative, model-facing constraints from the deterministic resource contract."""
    if not isinstance(contract, dict) or not contract:
        return ""
    lines: list[str] = []
    canvas = contract.get("primary_canvas")
    model = contract.get("render_model")
    lib = contract.get("render_lib")
    if canvas and model == "webgl":
        via = f" via {lib}" if lib else ""
        lines.append(
            f"RENDER SURFACE: canvas#{canvas} is a WebGL surface{via}. Render to it through "
            f"WebGL/{lib or 'WebGL'} ONLY. NEVER call {canvas}.getContext('2d') or attach a 2D "
            f"renderer to #{canvas}: a canvas allows only ONE context type, so requesting 2D makes "
            f"WebGLRenderer fail ('Error creating WebGL context') and the app renders nothing."
        )
    elif canvas and model == "canvas_2d":
        lines.append(
            f"RENDER SURFACE: canvas#{canvas} is a 2D canvas (getContext('2d')). Render through its "
            f"2D context ONLY — do NOT use WebGL or Three.js on #{canvas}."
        )
    if contract.get("external_libs"):
        lines.append(
            "EXTERNAL LIBS already loaded in index.html (use these globals; do not re-import or "
            "swap the library): " + ", ".join(contract["external_libs"])
        )
    if contract.get("dom_ids"):
        lines.append(
            "DOM ELEMENT IDS that exist in index.html (reference these EXACT ids; do not invent new "
            "ones or rename them): " + ", ".join("#" + i for i in contract["dom_ids"][:40])
        )
    if contract.get("globals_by_file"):
        parts = "; ".join(
            f"{path} defines [{', '.join(names)}]" for path, names in contract["globals_by_file"].items()
        )
        lines.append(
            "GLOBAL SYMBOLS defined by sibling files (consume these EXACT names across files; do not "
            "redefine or invent parallel ones): " + parts
        )
    return "\n".join(lines)


def render_contract_for_prompt(contract: dict[str, Any]) -> str:
    """Compact, model-facing rendering of the contract for injection into a generation prompt."""
    if not isinstance(contract, dict) or not contract.get("entities"):
        return ""
    lines: list[str] = []
    if contract.get("shared_state"):
        lines.append(f"SHARED STATE: {contract['shared_state']}")
    lines.append("ENTITIES (use these EXACT names / methods / properties):")
    for e in contract.get("entities") or []:
        api = ", ".join(e.get("methods") or [])
        props = ", ".join(e.get("properties") or [])
        bits = [f"- {e.get('name')}"]
        if e.get("kind"):
            bits.append(f"({e['kind']})")
        if props:
            bits.append(f"props: {props}")
        if api:
            bits.append(f"methods: {api}")
        if e.get("notes"):
            bits.append(f"— {e['notes']}")
        lines.append(" ".join(bits))
    if contract.get("wiring"):
        lines.append(f"WIRING (the main loop / init MUST connect entities exactly like this): {contract['wiring']}")
    if contract.get("init"):
        lines.append(f"INIT: {contract['init']}")
    return "\n".join(lines)
