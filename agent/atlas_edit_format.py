"""SEARCH/REPLACE edit-block parsing for weak-model large-file edits.

A weak local model produces a nested JSON ``edits`` array (each {old_string, new_string} carefully
escaped) much LESS reliably than an Aider-style SEARCH/REPLACE block, which is mostly verbatim code:

    js/main.js
    <<<<<<< SEARCH
    const r = new Renderer(canvas.getContext('2d'));
    =======
    const engine = new GameEngine();
    >>>>>>> REPLACE

This module parses such blocks (wherever the model puts them — a dedicated field, ``proposed_content``,
or free text) into the {path, old_string, new_string} edits the apply path already understands. It is
deterministic; the model only has to copy the old code and write the new code. Combined with the
WeakLargeFileEditPolicy output cap, this gives the weak model an output target it can actually hit.
"""
from __future__ import annotations

import re

# Tolerant markers: >=3 of < / = / > so a model that writes 5 or 8 of them still parses. SEARCH and
# REPLACE may carry trailing text on their line (e.g. a path); the divider line is === only.
_BLOCK_RE = re.compile(
    r"<{3,}\s*SEARCH\b[^\n]*\n(.*?)\n={3,}[^\n]*\n(.*?)\n>{3,}\s*REPLACE\b",
    re.DOTALL,
)
_PATH_RE = re.compile(r"^[\w./\\-]+\.[A-Za-z0-9]{1,8}$")
_FENCE_LANG_RE = re.compile(r"^[A-Za-z0-9+#-]{1,12}$")


def _path_before(text: str, idx: int) -> str | None:
    """Nearest file-path-looking line in the few lines before a block (Aider puts the filename just
    above the block, optionally after a ``` fence). Returns a normalized path or None."""
    for raw in reversed(str(text[:idx]).splitlines()[-6:]):
        s = raw.strip().strip("`").strip()
        if s.startswith("```"):
            s = s[3:].strip()
        if not s:
            continue
        if _PATH_RE.match(s):
            return s.replace("\\", "/")
        if _FENCE_LANG_RE.match(s):
            continue  # a bare ```js language token — keep scanning upward
        break  # some other prose line — stop (avoid grabbing a random word)
    return None


def parse_search_replace_blocks(text: str, default_path: str | None = None) -> list[dict]:
    """Parse SEARCH/REPLACE blocks in ``text`` into [{path, old_string, new_string}].

    ``path`` is taken from a filename line just above each block, else ``default_path`` (the single
    target of an edit-only generation). Blocks with no resolvable path are dropped. Returns [] when
    there are no well-formed blocks."""
    text = str(text or "")
    if "SEARCH" not in text or "REPLACE" not in text:
        return []
    out: list[dict] = []
    for m in _BLOCK_RE.finditer(text):
        old_string = m.group(1)
        new_string = m.group(2)
        path = _path_before(text, m.start()) or default_path
        if not path:
            continue
        out.append({
            "path": str(path).replace("\\", "/"),
            "old_string": old_string,
            "new_string": new_string,
        })
    return out


def harvest_search_replace_edits(output: dict, default_path: str | None = None) -> list[dict]:
    """Scan the LLM output's text-bearing fields for SEARCH/REPLACE blocks and return parsed edits.

    Robust to where a weak model places them: a dedicated ``search_replace`` field, the catch-all
    ``proposed_content``/``proposed_fix``, or a string ``edits`` value. First field that yields blocks
    wins. Returns [] if none are found (caller falls back to the normal edits/content path)."""
    if not isinstance(output, dict):
        return []
    for key in ("search_replace", "edits", "proposed_content", "proposed_fix", "summary"):
        val = output.get(key)
        if isinstance(val, str) and "SEARCH" in val and "REPLACE" in val:
            blocks = parse_search_replace_blocks(val, default_path=default_path)
            if blocks:
                return blocks
    return []
