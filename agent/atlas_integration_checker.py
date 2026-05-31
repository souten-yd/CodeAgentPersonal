from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

# Patterns for HTML script src references
_SCRIPT_SRC = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
# Patterns for HTML link href references (CSS)
_LINK_HREF = re.compile(r'<link[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
# ES module import patterns (static `import ... from "x"` and bare `import "x"`)
_ES_IMPORT = re.compile(r'(?:^|\s)import\s+(?:\{[^}]*\}|[\w*]+|\*\s+as\s+\w+)\s+from\s+["\']([^"\']+)["\']',
                         re.MULTILINE)
_ES_IMPORT_BARE = re.compile(r'(?:^|\s)import\s+["\']([^"\']+)["\']', re.MULTILINE)
# Dynamic import("x")
_ES_DYNAMIC_IMPORT = re.compile(r'\bimport\s*\(\s*["\']([^"\']+)["\']\s*\)')
# CommonJS require
_CJS_REQUIRE = re.compile(r'\brequire\s*\(\s*["\']([^"\']+)["\']\s*\)')
# Python import
_PY_IMPORT = re.compile(r'^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE)
# Exported symbols (named declarations + `export { a, b }`)
_ES_EXPORT_DECL = re.compile(r'\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)')
_ES_EXPORT_LIST = re.compile(r'\bexport\s*\{([^}]*)\}')

_DISCONNECTED_WARNING = "warning"
_DISCONNECTED_FAILED = "failed"
_LOCAL_JS_EXT = (".js", ".mjs", ".ts")
_EXTERNAL_PREFIXES = ("http://", "https://", "//", "data:", "blob:", "mailto:")


def _is_external(ref: str) -> bool:
    return any(ref.startswith(p) for p in _EXTERNAL_PREFIXES)


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

    def check_entrypoint_import_graph(self, html_path: str | Path, *, project_root: str | Path,
                                      generated_files: list[str]) -> dict:
        """Follow the JS import graph from the HTML entrypoint and report unreachable modules.

        Unlike check_html_entrypoint (direct references only), this resolves `<script src>`
        entry modules and walks their ES imports / require / dynamic imports transitively,
        so a module imported by main.js (which IS in the HTML) counts as reachable. CSS is
        still matched by direct <link href> reference.

        Returns:
            {status, reachable, disconnected, findings, unused_exports}
        """
        html_path = Path(html_path)
        project_root = Path(project_root)
        if not html_path.exists():
            return {"status": "failed", "reachable": [], "disconnected": list(generated_files),
                    "findings": [{"type": "entrypoint_missing", "path": str(html_path)}], "unused_exports": []}
        try:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "reachable": [], "disconnected": list(generated_files),
                    "findings": [{"type": "entrypoint_read_error", "detail": str(exc)}], "unused_exports": []}

        html_rel_dir = self._rel_dir(html_path, project_root)
        script_refs = [r for r in _SCRIPT_SRC.findall(html) if not _is_external(r)]
        css_refs = set(_LINK_HREF.findall(html))

        # BFS over the JS import graph starting from entry scripts.
        reachable: set[str] = set()
        queue: list[str] = []
        for ref in script_refs:
            entry = self._normalize_join(html_rel_dir, ref)
            if entry:
                queue.append(entry)
        contents: dict[str, str] = {}
        while queue:
            rel = queue.pop()
            rel = self._with_js_ext(project_root, rel)
            if not rel or rel in reachable:
                continue
            fp = project_root / rel
            if not fp.exists():
                continue
            reachable.add(rel)
            try:
                src = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            contents[rel] = src
            importer_dir = str(PurePosixPath(rel).parent)
            for source in self._import_sources(src):
                if _is_external(source):
                    continue
                target = self._normalize_join(importer_dir, source)
                if target:
                    queue.append(target)

        connected: list[str] = []
        disconnected: list[str] = []
        findings: list[dict] = []
        for gen in generated_files:
            gen_norm = str(gen).replace("\\", "/").lstrip("./")
            low = gen_norm.lower()
            if low.endswith(".css"):
                referenced = any(gen_norm in r or PurePosixPath(gen_norm).name in r for r in css_refs)
            elif low.endswith(_LOCAL_JS_EXT):
                referenced = gen_norm in reachable or any(gen_norm in r for r in script_refs)
            else:
                continue
            if referenced:
                connected.append(gen)
            else:
                disconnected.append(gen)
                severity = _DISCONNECTED_FAILED if _is_user_facing(gen) else _DISCONNECTED_WARNING
                findings.append({
                    "type": "disconnected_module",
                    "severity": severity,
                    "path": gen,
                    "detail": f"{gen} is not reachable from {html_path.name} import graph",
                })

        # Best-effort: exported symbols from reachable modules never imported anywhere.
        unused_exports = self._unused_exports(contents)
        for sym in unused_exports:
            findings.append({"type": "unused_export", "severity": "warning", **sym})

        status = "failed" if any(f["severity"] == "failed" for f in findings) else \
            "warned" if findings else "passed"
        return {"status": status, "reachable": sorted(reachable), "disconnected": disconnected,
                "findings": findings, "unused_exports": unused_exports}

    def _import_sources(self, src: str) -> list[str]:
        out: list[str] = []
        for rx in (_ES_IMPORT, _ES_IMPORT_BARE, _ES_DYNAMIC_IMPORT, _CJS_REQUIRE):
            out += rx.findall(src)
        return out

    def _unused_exports(self, contents: dict[str, str]) -> list[dict]:
        """Find exported symbols in reachable modules that are never imported/used elsewhere."""
        # Collect imported names and identifier usages across all reachable modules.
        used: set[str] = set()
        for src in contents.values():
            for block in _ES_IMPORT.findall(src):
                pass  # source paths handled separately
            for m in re.finditer(r'import\s+\{([^}]*)\}\s+from', src):
                for name in m.group(1).split(","):
                    n = name.split(" as ")[0].strip()
                    if n:
                        used.add(n)
            for m in re.finditer(r'import\s+(\w+)\s+from', src):
                used.add(m.group(1))
        # Identifier usage (calls / references) across all modules.
        all_src = "\n".join(contents.values())
        unused: list[dict] = []
        for rel, src in contents.items():
            exported: set[str] = set(_ES_EXPORT_DECL.findall(src))
            for m in _ES_EXPORT_LIST.finditer(src):
                for name in m.group(1).split(","):
                    n = name.split(" as ")[0].strip()
                    if n:
                        exported.add(n)
            for sym in exported:
                if sym in used:
                    continue
                # Count references outside the declaring file; if only the declaration exists, unused.
                others = all_src.count(sym) - src.count(sym)
                if others <= 0 and not re.search(rf'\b{re.escape(sym)}\s*\(', all_src.replace(src, "")):
                    unused.append({"path": rel, "symbol": sym})
        return unused

    @staticmethod
    def _rel_dir(file_path: Path, project_root: Path) -> str:
        try:
            rel = file_path.resolve().relative_to(project_root.resolve())
            return str(PurePosixPath(rel).parent)
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _normalize_join(base_dir: str, source: str) -> str:
        """Join an import source against a base dir and normalize ../ and ./ to a project-rel path."""
        source = source.strip().lstrip("/")
        combined = source if (base_dir in ("", ".")) else f"{base_dir}/{source}"
        parts: list[str] = []
        for p in combined.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(p)
        return "/".join(parts)

    @staticmethod
    def _with_js_ext(project_root: Path, rel: str) -> str:
        """Add .js when an extension-less import resolves to a real .js/.mjs/.ts file."""
        if rel.lower().endswith((".js", ".mjs", ".ts", ".css", ".json")):
            return rel
        for ext in _LOCAL_JS_EXT:
            if (project_root / (rel + ext)).exists():
                return rel + ext
        return rel

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
