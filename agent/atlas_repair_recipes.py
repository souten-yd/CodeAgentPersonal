"""Deterministic repair recipes for known bug signatures.

A weak model cannot reliably hand-author a fix; but many recurring defects have a known, mechanical
remedy. A repair recipe encodes that remedy so the LLM is removed from the critical path — at most it
PICKS among options; the actual edit is applied deterministically. This complements the detection
gates (e.g. the WebGL-vs-2D canvas gate): the gate says "this is broken", the recipe says "here is
the exact safe fix".

First recipe: ``webgl_canvas_2d_context_conflict`` — a file takes a 2D context on the app's WebGL
canvas (a canvas allows only one context type, so WebGLRenderer fails and nothing renders). The
SAFE, fully deterministic case is the one observed live: the 2D context is acquired into a variable
that is never used (dead code, e.g. ``const renderer = new Renderer(canvas.getContext('2d'));`` where
``renderer`` is unused) — that statement is simply removed. When the 2D context IS used elsewhere the
recipe does NOT guess (removing live code is unsafe); it returns the options A/B/C for an LLM/human
to choose.
"""
from __future__ import annotations

import re

# A canvas-bound variable: const/let/var X = document.getElementById('<canvas>')
def _canvas_bound_vars(text: str, canvas_id: str) -> set[str]:
    pat = re.compile(
        rf"(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(\s*['\"]{re.escape(canvas_id)}['\"]\s*\)"
    )
    return set(pat.findall(text))


def _line_takes_2d_on_canvas(line: str, canvas_id: str, bound_vars: set[str]) -> bool:
    if "getContext" not in line or "2d" not in line.lower():
        return False
    if re.search(rf"getElementById\(\s*['\"]{re.escape(canvas_id)}['\"]\s*\)\s*\.\s*getContext\(\s*['\"]2d['\"]", line):
        return True
    return any(re.search(rf"\b{re.escape(v)}\s*\.\s*getContext\(\s*['\"]2d['\"]", line) for v in bound_vars)


WEBGL_2D_OPTIONS = [
    {"id": "A", "summary": "Render the 2D HUD on a SEPARATE overlay <canvas> (its own id), not the WebGL canvas."},
    {"id": "B", "summary": "Move the HUD to an HTML/CSS DOM overlay; remove the 2D canvas drawing entirely."},
    {"id": "C", "summary": "Remove the getContext('2d') acquisition on the WebGL canvas (the WebGL renderer owns it)."},
]


def _overlay_canvas_replacement(line: str, canvas_id: str, bound_vars: set[str]) -> dict:
    m = re.match(
        r"(?P<indent>\s*)(?:const|let|var)\s+(?P<var>\w+)\s*=\s*(?P<expr>.+?)\.getContext\(\s*['\"]2d['\"]\s*\)\s*;?\s*$",
        line,
    )
    if not m:
        return {"applied": False, "reason": "option_a_requires_simple_context_declaration"}
    var = m.group("var")
    expr = m.group("expr").strip()
    indent = m.group("indent") or ""
    if expr.startswith("document.getElementById"):
        canvas_ref = f"document.getElementById('{canvas_id}')"
    elif expr in bound_vars:
        canvas_ref = expr
    else:
        return {"applied": False, "reason": "option_a_canvas_reference_unresolved"}
    overlay_var = f"{var}OverlayCanvas"
    replacement = (
        f"{indent}const {overlay_var} = document.createElement('canvas');\n"
        f"{indent}{overlay_var}.id = '{canvas_id}-2d-overlay';\n"
        f"{indent}{overlay_var}.width = {canvas_ref}.width;\n"
        f"{indent}{overlay_var}.height = {canvas_ref}.height;\n"
        f"{indent}{overlay_var}.style.position = 'absolute';\n"
        f"{indent}{overlay_var}.style.inset = '0';\n"
        f"{indent}{overlay_var}.style.pointerEvents = 'none';\n"
        f"{indent}{canvas_ref}.parentElement?.appendChild({overlay_var});\n"
        f"{indent}const {var} = {overlay_var}.getContext('2d');\n"
    )
    return {"applied": True, "replacement": replacement}


def repair_webgl_2d_conflict(content: str, canvas_id: str, *, selected_option_id: str = "") -> dict:
    """Deterministically remove a DEAD 2D-context acquisition on the WebGL canvas.

    Returns {"applied": True, "new_content", "removed": [lines], "recipe": "remove_dead_2d_context"}
    when every conflicting statement is a declaration whose bound variable is unused (safe to delete).
    Otherwise {"applied": False, "reason", "options"}: the 2D context is used, so the fix needs a
    real code change (options A/B/C) — never guessed here. If a caller has an explicit selected
    option, the recipe applies only deterministic transformations it can prove locally.
    """
    text = str(content or "")
    cid = str(canvas_id or "").strip()
    if not cid or "getContext" not in text:
        return {"applied": False, "reason": "no_conflict", "options": []}
    bound = _canvas_bound_vars(text, cid)
    lines = text.splitlines(keepends=True)
    conflict_idxs = [i for i, ln in enumerate(lines) if _line_takes_2d_on_canvas(ln, cid, bound)]
    if not conflict_idxs:
        return {"applied": False, "reason": "no_conflict", "options": []}

    removable: list[int] = []
    removed_text: list[str] = []
    for i in conflict_idxs:
        line = lines[i]
        m = re.match(r"\s*(?:const|let|var)\s+(\w+)\s*=", line)
        if not m:
            # not a simple declaration (e.g. a bare expression or property assignment) -> not safe
            return {"applied": False, "reason": "2d_context_not_a_dead_declaration", "options": WEBGL_2D_OPTIONS}
        var = m.group(1)
        # uses of the variable anywhere EXCEPT its own declaration line
        uses = sum(len(re.findall(rf"\b{re.escape(var)}\b", lines[j])) for j in range(len(lines)) if j != i)
        if uses > 0:
            selected = str(selected_option_id or "").strip().upper()
            if selected == "A":
                repl = _overlay_canvas_replacement(line, cid, bound)
                if not repl.get("applied"):
                    return {**repl, "options": WEBGL_2D_OPTIONS}
                new_lines = list(lines)
                new_lines[i] = str(repl["replacement"])
                return {
                    "applied": True,
                    "new_content": "".join(new_lines),
                    "recipe": "webgl_2d_option_a_overlay_canvas",
                    "selected_option_id": "A",
                    "replaced": line.strip(),
                }
            if selected:
                return {"applied": False, "reason": "selected_option_not_implemented", "selected_option_id": selected, "options": WEBGL_2D_OPTIONS}
            return {"applied": False, "reason": "2d_context_in_use", "options": WEBGL_2D_OPTIONS}
        removable.append(i)
        removed_text.append(line.strip())

    new_lines = [ln for i, ln in enumerate(lines) if i not in set(removable)]
    return {
        "applied": True,
        "new_content": "".join(new_lines),
        "removed": removed_text,
        "recipe": "remove_dead_2d_context",
    }


def apply_known_bug_repairs(content: str, resource_contract: dict | None) -> dict:
    """Dispatch deterministic repairs based on the shared-resource contract. Currently handles the
    WebGL-vs-2D canvas conflict. Returns the recipe result (``applied`` False when nothing applied)."""
    if not isinstance(resource_contract, dict):
        return {"applied": False, "reason": "no_contract"}
    if resource_contract.get("render_model") == "webgl" and resource_contract.get("primary_canvas"):
        return repair_webgl_2d_conflict(
            content,
            str(resource_contract.get("primary_canvas")),
            selected_option_id=str(resource_contract.get("selected_repair_option_id") or ""),
        )
    return {"applied": False, "reason": "no_recipe"}
