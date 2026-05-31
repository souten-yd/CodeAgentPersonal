from __future__ import annotations

import re
from pathlib import Path

# Max lines for a single HTML file before God source warning
_HTML_MAX_INLINE_SCRIPT_LINES = 80
# Max lines for a single JS file before God object warning
_JS_MAX_LINES = 600

_INLINE_SCRIPT = re.compile(r'<script(?:\s[^>]*)?>.*?</script>', re.DOTALL | re.IGNORECASE)

# Recommended modular slice layout for small HTML/JS/CSS apps
RECOMMENDED_SLICE_LAYOUT = [
    "index.html",
    "css/style.css",
    "js/main.js",
    "js/state.js",
    "js/input.js",
    "js/renderer.js",
]


def check_god_source(files: dict[str, str]) -> list[dict]:
    """Check for God source patterns in generated files.

    Returns a list of findings: {type, path, severity, detail}
    """
    findings: list[dict] = []

    for path, content in files.items():
        path_lower = path.lower().replace("\\", "/")

        if path_lower.endswith(".html"):
            inline_scripts = _INLINE_SCRIPT.findall(content)
            total_inline_lines = sum(s.count("\n") for s in inline_scripts)
            if total_inline_lines > _HTML_MAX_INLINE_SCRIPT_LINES:
                findings.append({
                    "type": "god_source_html_inline_script",
                    "path": path,
                    "severity": "warning",
                    "detail": (
                        f"HTML contains {total_inline_lines} lines of inline script "
                        f"(limit: {_HTML_MAX_INLINE_SCRIPT_LINES}). "
                        "Move logic to separate JS modules."
                    ),
                })

        if path_lower.endswith((".js", ".ts", ".mjs")) and "test" not in path_lower:
            line_count = content.count("\n") + 1
            if line_count > _JS_MAX_LINES:
                findings.append({
                    "type": "god_source_js_oversized",
                    "path": path,
                    "severity": "warning",
                    "detail": (
                        f"JS file has {line_count} lines (limit: {_JS_MAX_LINES}). "
                        "Consider splitting into modular vertical slices."
                    ),
                })

    return findings


def check_disconnected_modules(
    entrypoint_references: set[str],
    generated_files: list[str],
) -> list[dict]:
    """Check for generated JS/CSS files not referenced from the entrypoint.

    Returns findings for disconnected modules.
    """
    findings: list[dict] = []
    for gen_file in generated_files:
        gen_name = Path(gen_file).name
        gen_norm = gen_file.replace("\\", "/")
        if not any(gen_name in ref or gen_norm in ref for ref in entrypoint_references):
            findings.append({
                "type": "disconnected_module",
                "path": gen_file,
                "severity": "warning",
                "detail": f"{gen_file} is generated but not referenced from the entrypoint.",
            })
    return findings


def suggest_modular_layout(task_description: str) -> list[str]:
    """Return a recommended modular file layout for small HTML/JS apps."""
    desc_lower = task_description.lower()
    layout = list(RECOMMENDED_SLICE_LAYOUT)
    if "collision" in desc_lower or "entity" in desc_lower or "game" in desc_lower:
        layout += ["js/entities.js", "js/collision.js"]
    if "canvas" in desc_lower:
        layout = [f for f in layout if f != "css/style.css"] + ["css/style.css"]
    return layout
