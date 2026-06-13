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
