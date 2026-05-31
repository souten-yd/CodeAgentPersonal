from __future__ import annotations

import re
from pathlib import Path

# Patterns that indicate placeholder/stub implementation (not docs/tests)
_PLACEHOLDER_PATTERNS = [
    (re.compile(r'#\s*placeholder', re.IGNORECASE), 'placeholder_comment'),
    (re.compile(r'#\s*TODO\b', re.IGNORECASE), 'todo_comment'),
    (re.compile(r'#\s*in\s+a\s+real\s+implementation', re.IGNORECASE), 'in_real_impl_comment'),
    (re.compile(r'#\s*FIXME\b', re.IGNORECASE), 'fixme_comment'),
    (re.compile(r'//\s*placeholder', re.IGNORECASE), 'js_placeholder_comment'),
    (re.compile(r'//\s*TODO\b', re.IGNORECASE), 'js_todo_comment'),
    (re.compile(r'//\s*in\s+a\s+real\s+implementation', re.IGNORECASE), 'js_in_real_impl_comment'),
    (re.compile(r'\bpass\s*$', re.MULTILINE), 'empty_pass_body'),
    (re.compile(r'\breturn\s+None\s*#.*stub', re.IGNORECASE), 'stub_return_none'),
    (re.compile(r'console\.log\s*\(["\'].*(?:placeholder|todo|stub|not\s+impl)', re.IGNORECASE),
     'console_log_placeholder'),
]

# Patterns for empty function/method bodies (draw/update/check with only pass or comment)
_EMPTY_BODY_PATTERNS = [
    re.compile(r'\bdef\s+(?:draw|update|check|render|tick|step)\s*\([^)]*\)\s*:\s*\n\s+pass\b',
               re.MULTILINE),
    re.compile(r'\bfunction\s+(?:draw|update|check|render|tick|step)\s*\([^)]*\)\s*\{[^}]*\}',
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


def scan_file_for_placeholders(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return detect_placeholders(content, file_path=str(path))
