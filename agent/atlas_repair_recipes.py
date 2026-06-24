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


def repair_webgl_2d_conflict(content: str, canvas_id: str) -> dict:
    """Deterministically remove a DEAD 2D-context acquisition on the WebGL canvas.

    Returns {"applied": True, "new_content", "removed": [lines], "recipe": "remove_dead_2d_context"}
    when every conflicting statement is a declaration whose bound variable is unused (safe to delete).
    Otherwise {"applied": False, "reason", "options"}: the 2D context is used, so the fix needs a
    real code change (options A/B/C) — never guessed here.
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
        return repair_webgl_2d_conflict(content, str(resource_contract.get("primary_canvas")))
    return {"applied": False, "reason": "no_recipe"}
