from __future__ import annotations

import re
from pathlib import Path

# Patterns for HTML script src references
_SCRIPT_SRC = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
# Patterns for HTML link href references (CSS)
_LINK_HREF = re.compile(r'<link[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
# ES module import patterns
_ES_IMPORT = re.compile(r'(?:^|\s)import\s+(?:\{[^}]*\}|[\w*]+|\*\s+as\s+\w+)\s+from\s+["\']([^"\']+)["\']',
                         re.MULTILINE)
# CommonJS require
_CJS_REQUIRE = re.compile(r'\brequire\s*\(\s*["\']([^"\']+)["\']\s*\)')
# Python import
_PY_IMPORT = re.compile(r'^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE)

_DISCONNECTED_WARNING = "warning"
_DISCONNECTED_FAILED = "failed"


class AtlasIntegrationChecker:
    """Check that generated files are connected to the entrypoint and used in the runtime path."""

    def check_html_entrypoint(self, html_path: str | Path, *, generated_files: list[str]) -> dict:
        """Verify that all generated JS/CSS files are referenced from the HTML entrypoint.

        Returns:
            {
                status: "passed" | "warned" | "failed",
                connected: list[str],
                disconnected: list[str],
                findings: list[dict],
            }
        """
        html_path = Path(html_path)
        if not html_path.exists():
            return self._result("failed", connected=[], disconnected=generated_files,
                                findings=[{"type": "entrypoint_missing", "path": str(html_path)}])

        try:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return self._result("failed", connected=[], disconnected=generated_files,
                                findings=[{"type": "entrypoint_read_error", "detail": str(exc)}])

        script_refs = set(_SCRIPT_SRC.findall(html))
        css_refs = set(_LINK_HREF.findall(html))
        all_refs = script_refs | css_refs

        connected: list[str] = []
        disconnected: list[str] = []
        findings: list[dict] = []

        for gen_file in generated_files:
            gen_name = Path(gen_file).name
            gen_path_norm = gen_file.replace("\\", "/")
            # Check if the generated file is referenced in HTML (by name or relative path)
            referenced = any(
                gen_name in ref or gen_path_norm in ref or gen_path_norm.lstrip("./") in ref
                for ref in all_refs
            )
            if referenced:
                connected.append(gen_file)
            else:
                disconnected.append(gen_file)
                severity = _DISCONNECTED_FAILED if _is_user_facing(gen_file) else _DISCONNECTED_WARNING
                findings.append({
                    "type": "disconnected_module",
                    "severity": severity,
                    "path": gen_file,
                    "detail": f"{gen_file} not referenced from {html_path.name}",
                })

        if any(f["severity"] == "failed" for f in findings):
            status = "failed"
        elif findings:
            status = "warned"
        else:
            status = "passed"

        return self._result(status, connected=connected, disconnected=disconnected, findings=findings)

    def check_import_consistency(self, files: dict[str, str]) -> dict:
        """Check that JS/TS exports and imports are consistent across files.

        Args:
            files: {rel_path: content}

        Returns:
            {status, findings}
        """
        exports: dict[str, list[str]] = {}
        findings: list[dict] = []

        for path, content in files.items():
            if not path.endswith((".js", ".ts", ".mjs")):
                continue
            exported = re.findall(r'\bexport\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)',
                                   content)
            exports[path] = exported

        for path, content in files.items():
            if not path.endswith((".js", ".ts", ".mjs")):
                continue
            for m in _ES_IMPORT.finditer(content):
                source = m.group(1)
                if source.startswith((".", "/")):
                    # Relative import — check if target file is in our set
                    if not any(source.replace("./", "").replace("../", "") in k for k in files):
                        findings.append({
                            "type": "unresolved_relative_import",
                            "severity": "warning",
                            "path": path,
                            "import_source": source,
                        })

        status = "failed" if any(f["severity"] == "failed" for f in findings) else \
            "warned" if findings else "passed"
        return {"status": status, "findings": findings}

    @staticmethod
    def _result(status: str, *, connected: list, disconnected: list, findings: list) -> dict:
        return {"status": status, "connected": connected, "disconnected": disconnected, "findings": findings}


def _is_user_facing(path: str) -> bool:
    """Heuristic: files like renderer.js, main.js, state.js are user-facing."""
    p = Path(path).stem.lower()
    non_user = {"test", "spec", "mock", "fixture", "stub"}
    return p not in non_user
