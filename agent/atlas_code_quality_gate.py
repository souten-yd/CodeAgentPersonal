"""Deterministic code-quality gate: syntax validity + LLM reasoning-leak detection.

Two gaps this closes, both surfaced by a weak model generating the hardest integration file:
1. SYNTAX: a `.js` file with a real parse error (e.g. a duplicate `const`) was applied and marked
   "completed" because the auto-verifier only runs a (deferrable) whole-app browser smoke or pytest —
   it never ran `node --check` on the generated source file. This module provides a cheap, mandatory
   `node --check` / `py_compile` check on file CONTENT (a temp file), usable both at generation time
   (reject -> regenerate) and at apply-time verification (hard fail).
2. REASONING LEAK: a weak model can dump its chain-of-thought into the code as comments
   ("// I will assume `lastFireTime` is declared...", "// Wait, looking at the skeleton..."). That is
   not real implementation and usually rides along with undefined-variable / logic defects. We detect
   a DENSITY of such comments so a genuine incidental "// TODO"-style note does not trip it.

No network. Node is optional: if `node` is not on PATH the JS syntax check is a no-op pass (never
block on tooling absence). Python uses the built-in compiler (always available).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

_JS_EXTS = {".js", ".mjs", ".cjs", ".jsx"}
_PY_EXTS = {".py"}

# Comment lines that read as first-person deliberation / prompt-reasoning rather than documentation.
_REASONING_LEAK_PATTERNS = (
    re.compile(r"//.*\bI['’]?ll\b", re.IGNORECASE),
    re.compile(r"//.*\bI will\b", re.IGNORECASE),
    re.compile(r"//.*\bI (?:can|cannot|can't|should|need to|assume|will assume)\b", re.IGNORECASE),
    re.compile(r"//.*\b(?:Let's|Lets)\b", re.IGNORECASE),
    re.compile(r"//.*\bWait,", re.IGNORECASE),
    re.compile(r"//.*\bthe prompt says\b", re.IGNORECASE),
    re.compile(r"//.*\b(?:the )?skeleton (?:doesn't|does not|shows|provided|snippet)\b", re.IGNORECASE),
    re.compile(r"//.*\blooking at (?:the|`)\b", re.IGNORECASE),
    re.compile(r"#.*\bI['’]?ll\b|#.*\bI will\b|#.*\bLet's\b|#.*\bWait,", re.IGNORECASE),
)
# At/above this many leak-pattern lines, treat the file as reasoning-contaminated (not a stray note).
_REASONING_LEAK_THRESHOLD = 3


def detect_reasoning_leak(content: str) -> list[str]:
    """Return the leaked-reasoning comment lines (trimmed) when their count reaches the threshold,
    else []. Empty for clean code and for one or two incidental notes."""
    hits: list[str] = []
    for line in str(content or "").splitlines():
        s = line.strip()
        if not s or not (s.startswith("//") or s.startswith("#") or "//" in s or "#" in s):
            continue
        if any(p.search(line) for p in _REASONING_LEAK_PATTERNS):
            hits.append(s[:160])
    return hits if len(hits) >= _REASONING_LEAK_THRESHOLD else []


def check_syntax(content: str, file_path: str) -> tuple[bool, str]:
    """(ok, error). Checks `.js/.mjs/.cjs/.jsx` via `node --check` and `.py` via the built-in
    compiler. Unknown extensions and a missing `node` are a PASS (never block on tooling absence)."""
    ext = os.path.splitext(str(file_path or ""))[1].lower()
    text = str(content or "")
    if ext in _PY_EXTS:
        try:
            compile(text, str(file_path or "<generated>"), "exec")
            return True, ""
        except SyntaxError as exc:
            return False, f"py_syntax_error: {exc.msg} (line {exc.lineno})"
    if ext in _JS_EXTS:
        return _node_check(text, ext)
    return True, ""


def _node_check(text: str, ext: str) -> tuple[bool, str]:
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False, encoding="utf-8") as f:
            f.write(text)
            tmp = f.name
        try:
            proc = subprocess.run(
                ["node", "--check", tmp],
                capture_output=True, text=True, timeout=30,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
        except FileNotFoundError:
            return True, ""  # node not installed -> do not block
        except subprocess.TimeoutExpired:
            return True, ""  # be lenient on a hung checker
        if proc.returncode == 0:
            return True, ""
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        # Node prints the file path (the temp name) + the SyntaxError line; surface the message only.
        msg = next((ln for ln in err if "Error" in ln), (err[-1] if err else "syntax error"))
        return False, f"js_syntax_error: {msg.strip()[:200]}"
    except Exception:  # noqa: BLE001 - never block generation on the checker itself.
        return True, ""
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def code_quality_findings(content: str, file_path: str) -> list[str]:
    """Combined blocking findings for a generated source file: a hard syntax error and/or a density
    of leaked reasoning comments. Empty list = acceptable. Cheap and deterministic."""
    findings: list[str] = []
    ok, err = check_syntax(content, file_path)
    if not ok and err:
        findings.append(err)
    leak = detect_reasoning_leak(content)
    if leak:
        findings.append(f"reasoning_leak: {len(leak)} deliberation comment(s) leaked into code, e.g. {leak[0]!r}")
    return findings
