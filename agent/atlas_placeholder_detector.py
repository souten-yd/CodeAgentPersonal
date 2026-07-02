from __future__ import annotations

import re
from pathlib import Path

# Patterns that indicate placeholder/stub implementation (not docs/tests)
_PLACEHOLDER_PATTERNS = [
    (re.compile(r'#\s*placeholder', re.IGNORECASE), 'placeholder_comment'),
    (re.compile(r'#\s*TODO\b', re.IGNORECASE), 'todo_comment'),
    (re.compile(r'#\s*(?:not\s+implemented|implement\s+(?:me|this|later)|stub)\b', re.IGNORECASE), 'python_placeholder_comment'),
    (re.compile(r'#\s*in\s+a\s+real\s+implementation', re.IGNORECASE), 'in_real_impl_comment'),
    (re.compile(r'#\s*FIXME\b', re.IGNORECASE), 'fixme_comment'),
    (re.compile(r'//\s*placeholder', re.IGNORECASE), 'js_placeholder_comment'),
    (re.compile(r'//\s*TODO\b', re.IGNORECASE), 'js_todo_comment'),
    (re.compile(r'//\s*(?:not\s+implemented|implement\s+(?:me|this|later)|stub)\b', re.IGNORECASE), 'js_placeholder_comment'),
    (re.compile(r'//\s*in\s+a\s+real\s+implementation', re.IGNORECASE), 'js_in_real_impl_comment'),
    (re.compile(r'/\*\s*(?:TODO|FIXME|placeholder|not\s+implemented|stub)', re.IGNORECASE), 'block_placeholder_comment'),
    (re.compile(r'<!--\s*(?:TODO|FIXME|placeholder|content\s+goes\s+here|not\s+implemented)', re.IGNORECASE), 'html_placeholder_comment'),
    (re.compile(r'\bpass\s*$', re.MULTILINE), 'empty_pass_body'),
    (re.compile(r'\.\.\.\s*$', re.MULTILINE), 'ellipsis_body'),
    (re.compile(r'\breturn\s+None\s*#.*stub', re.IGNORECASE), 'stub_return_none'),
    (re.compile(r'\b(?:throw\s+new\s+Error|raise\s+NotImplementedError)\s*\([^)]*(?:TODO|not\s+implemented|stub)', re.IGNORECASE), 'not_implemented_throw'),
    (re.compile(r'console\.log\s*\(["\'].*(?:placeholder|todo|stub|not\s+impl)', re.IGNORECASE),
     'console_log_placeholder'),
]

# Patterns for empty function/method bodies (draw/update/check with only pass or comment)
_EMPTY_BODY_PATTERNS = [
    re.compile(r'\bdef\s+(?:draw|update|check|render|tick|step|handle|process|execute)\s*\([^)]*\)\s*:\s*\n\s+(?:pass|\.\.\.|return\s+(?:None|False|True|0|1|""|\'\'))\b',
               re.MULTILINE),
    re.compile(r'\bfunction\s+(?:draw|update|check|render|tick|step|handle|process|execute)\s*\([^)]*\)\s*\{\s*(?://[^\n]*\n\s*)?(?:return\s+(?:false|true|null|undefined|0|1|["\'][^"\']*["\'])\s*;?)?\s*\}',
               re.MULTILINE),
]

# Intentional placeholder paths (docs, tests, fixtures) — skip these
_INTENTIONAL_PATHS = re.compile(
    r'(?:^|/)(test_|tests?/|spec/|docs?/|fixture|example|sample)',
    re.IGNORECASE,
)


def detect_placeholders(content: str, *, file_path: str = "") -> list[dict]:
    """Scan content for placeholder/stub patterns.

    Returns a list of findings: {type, line, snippet}.
    Intentional doc/test paths suppress warnings.
    """
    if _INTENTIONAL_PATHS.search(file_path.replace("\\", "/")):
        return []

    findings: list[dict] = []
    lines = content.splitlines()

    for pattern, ptype in _PLACEHOLDER_PATTERNS:
        for m in pattern.finditer(content):
            line_no = content[:m.start()].count('\n') + 1
            snippet = lines[line_no - 1].strip()[:120] if line_no <= len(lines) else ""
            findings.append({"type": ptype, "line": line_no, "snippet": snippet})

    for pattern in _EMPTY_BODY_PATTERNS:
        for m in pattern.finditer(content):
            line_no = content[:m.start()].count('\n') + 1
            findings.append({"type": "empty_function_body", "line": line_no, "snippet": m.group()[:80].strip()})

    # Deduplicate by (type, line)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for f in findings:
        key = (f["type"], f["line"])
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def is_placeholder_only_content(content: str, *, file_path: str = "") -> bool:
    """True if, after stripping comments/blanks, the file is essentially stubs (pass /
    console.log / empty bodies) AND it carries placeholder markers. Shared by the post-apply
    quality rollup and the pre-apply safe-apply gate so both judge "no real implementation"
    identically. The >2-substantive-line guard avoids false positives on small real files."""
    findings = detect_placeholders(content, file_path=file_path)
    if not findings:
        return False
    substantive = 0
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", "//", "/*", "*", "<!--")):
            continue
        if line in ("pass", "{", "}", "});", ")", "(", "</script>", "<script>"):
            continue
        if line.lower().startswith(("console.log", "todo", "pass", "return none")):
            continue
        substantive += 1
    return substantive <= 2


# Findings that are a genuine MISSING implementation (empty body, pass/…, not-implemented
# throw, stub return). One of these in production code blocks apply regardless of file size.
_STRUCTURAL_STUB_TYPES = frozenset({
    "empty_pass_body",
    "ellipsis_body",
    "empty_function_body",
    "not_implemented_throw",
    "stub_return_none",
})


def has_blocking_placeholder_content(content: str, *, file_path: str = "") -> bool:
    """True when a concrete implementation placeholder is present.

    A STRUCTURAL stub (empty critical method, ``pass``/``...`` body, ``NotImplementedError``,
    stub return) is a real missing implementation → always blocks, even a single one in an
    otherwise-large file. But a bare COMMENT marker (e.g. ``// Placeholder for X if needed`` or a
    lone ``// TODO``) inside otherwise-complete, substantive code is NOT a missing implementation —
    blocking a full, syntactically-valid file on one such comment is a false positive (see #2055).
    Comment-only markers therefore block only when the file is placeholder-DOMINANT.
    """
    findings = detect_placeholders(content, file_path=file_path)
    if not findings:
        return False
    if any(f.get("type") in _STRUCTURAL_STUB_TYPES for f in findings):
        return True
    return is_placeholder_only_content(content, file_path=file_path)


def scan_file_for_placeholders(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return detect_placeholders(content, file_path=str(path))
