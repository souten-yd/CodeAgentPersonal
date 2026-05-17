from __future__ import annotations

import ast
import re
from pathlib import Path

from agent.atlas_code_intel_schema import (
    AtlasDependencyEdge,
    AtlasDependencyGraphRequest,
    AtlasDependencyGraphResult,
    AtlasRelatedTestsRequest,
    AtlasRelatedTestsResult,
    AtlasSymbol,
    AtlasSymbolIndexRequest,
    AtlasSymbolIndexResult,
)
from agent.atlas_dev_tool_path import ensure_under_project, resolve_project_root, validate_relative_path

_EXCLUDED_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', '.cache', 'target', '.pytest_cache', 'ca_data'}
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]+\.(py|ts|tsx|js|jsx)|[^/]+\.(test|spec)\.(ts|tsx|js|jsx)|tests?/.*)$")


class AtlasCodeIntelService:
    def _iter_files(self, root: Path, relative_path: str, max_files: int):
        base = ensure_under_project(root, root / validate_relative_path(relative_path)) if relative_path else root
        out = []
        for path in base.rglob('*'):
            if any(part in _EXCLUDED_DIRS for part in path.parts):
                continue
            if path.is_file():
                out.append(path)
                if len(out) >= max_files:
                    break
        return out

    def _read_text(self, path: Path, max_bytes: int):
        data = path.read_bytes()
        if b"\x00" in data:
            return None, "binary file skipped"
        if len(data) > max_bytes:
            return None, "large file skipped"
        return data.decode("utf-8", errors="ignore"), ""

    def build_symbol_index(self, request: AtlasSymbolIndexRequest) -> AtlasSymbolIndexResult:
        root = resolve_project_root(request.project_path)
        symbols: list[AtlasSymbol] = []
        skipped_files: list[dict] = []
        warnings: list[str] = []
        files = self._iter_files(root, request.relative_path, request.max_files)
        for path in files:
            rel = path.relative_to(root).as_posix()
            text, skip_reason = self._read_text(path, request.max_bytes_per_file)
            if text is None:
                skipped_files.append({"path": rel, "reason": skip_reason})
                continue
            ext = path.suffix.lower()
            try:
                if ext == ".py":
                    tree = ast.parse(text)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            symbols.append(AtlasSymbol(name=node.name, kind="class", file_path=rel, line=node.lineno, column=node.col_offset))
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            parent = ""
                            kind = "function"
                            for maybe_parent in ast.walk(tree):
                                if isinstance(maybe_parent, ast.ClassDef) and node in maybe_parent.body:
                                    parent = maybe_parent.name
                                    kind = "method"
                                    break
                            sig = f"{node.name}({', '.join(arg.arg for arg in node.args.args)})"
                            symbols.append(AtlasSymbol(name=node.name, kind=kind, file_path=rel, line=node.lineno, column=node.col_offset, parent=parent, signature=sig))
                        elif isinstance(node, ast.Import):
                            for alias in node.names:
                                symbols.append(AtlasSymbol(name=alias.name, kind="import", file_path=rel, line=node.lineno, column=node.col_offset))
                        elif isinstance(node, ast.ImportFrom):
                            mod = node.module or ""
                            for alias in node.names:
                                symbols.append(AtlasSymbol(name=f"{mod}.{alias.name}".strip("."), kind="import", file_path=rel, line=node.lineno, column=node.col_offset))
                elif ext in {".js", ".ts", ".jsx", ".tsx"}:
                    for idx, line in enumerate(text.splitlines(), start=1):
                        for m in re.finditer(r"^\s*import\s+.+?from\s+['\"]([^'\"]+)['\"]", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind="import", file_path=rel, line=idx, column=m.start(1)))
                        for m in re.finditer(r"^\s*export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*([A-Za-z_$][\w$]*)?", line):
                            if m.group(1):
                                symbols.append(AtlasSymbol(name=m.group(1), kind="export", file_path=rel, line=idx, column=m.start(1)))
                        for m in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind="function", file_path=rel, line=idx, column=m.start(1)))
                        for m in re.finditer(r"\bclass\s+([A-Za-z_$][\w$]*)", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind="class", file_path=rel, line=idx, column=m.start(1)))
                        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind="variable", file_path=rel, line=idx, column=m.start(1), metadata={"arrow_function": True}))
                elif ext == ".html":
                    for idx, line in enumerate(text.splitlines(), start=1):
                        for m in re.finditer(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind="html_id", file_path=rel, line=idx, column=m.start(1)))
                elif ext == ".css":
                    for idx, line in enumerate(text.splitlines(), start=1):
                        for m in re.finditer(r"^\s*([^{@][^{]+)\{", line):
                            symbols.append(AtlasSymbol(name=m.group(1).strip(), kind="css_selector", file_path=rel, line=idx, column=m.start(1)))
                elif ext in {".md", ".markdown"}:
                    for idx, line in enumerate(text.splitlines(), start=1):
                        m = re.match(r"^(#{1,6})\s+(.+)", line)
                        if m:
                            symbols.append(AtlasSymbol(name=m.group(2).strip(), kind="variable", file_path=rel, line=idx, column=0, metadata={"heading_level": len(m.group(1))}))
            except SyntaxError:
                skipped_files.append({"path": rel, "reason": "syntax error"})
                warnings.append(f"syntax error skipped: {rel}")
            if len(symbols) >= request.max_symbols:
                symbols = symbols[:request.max_symbols]
                warnings.append("max_symbols limit reached")
                break
        return AtlasSymbolIndexResult(project_path=str(root), symbols=symbols, file_count=len(files), skipped_files=skipped_files, warnings=warnings, metadata={"relative_path": request.relative_path})

    def build_dependency_graph(self, request: AtlasDependencyGraphRequest) -> AtlasDependencyGraphResult:
        root = resolve_project_root(request.project_path)
        files = self._iter_files(root, request.relative_path, request.max_files)
        nodes: set[str] = set()
        edges: list[AtlasDependencyEdge] = []
        skipped_files: list[dict] = []
        warnings: list[str] = []
        for path in files:
            rel = path.relative_to(root).as_posix()
            nodes.add(rel)
            text, skip_reason = self._read_text(path, request.max_bytes_per_file)
            if text is None:
                skipped_files.append({"path": rel, "reason": skip_reason})
                continue
            ext = path.suffix.lower()
            for idx, line in enumerate(text.splitlines(), start=1):
                if ext == ".py":
                    for m in re.finditer(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", line):
                        tgt = m.group(1) or m.group(2)
                        edges.append(AtlasDependencyEdge(source=rel, target=tgt, kind="python_import", line=idx))
                elif ext in {".js", ".ts", ".jsx", ".tsx"}:
                    for m in re.finditer(r"import\s+.+?from\s+['\"]([^'\"]+)['\"]", line):
                        edges.append(AtlasDependencyEdge(source=rel, target=m.group(1), kind="js_import", line=idx))
                elif ext == ".html":
                    for m in re.finditer(r"<script[^>]*\bsrc=['\"]([^'\"]+)['\"]", line):
                        edges.append(AtlasDependencyEdge(source=rel, target=m.group(1), kind="html_script", line=idx))
                    for m in re.finditer(r"<link[^>]*\brel=['\"]stylesheet['\"][^>]*\bhref=['\"]([^'\"]+)['\"]", line):
                        edges.append(AtlasDependencyEdge(source=rel, target=m.group(1), kind="html_stylesheet", line=idx))
                elif ext == ".css":
                    for m in re.finditer(r"@import\s+(?:url\()?['\"]([^'\"]+)['\"]", line):
                        edges.append(AtlasDependencyEdge(source=rel, target=m.group(1), kind="css_import", line=idx))
            if len(edges) >= request.max_edges:
                edges = edges[:request.max_edges]
                warnings.append("max_edges limit reached")
                break
        nodes.update(edge.target for edge in edges)
        return AtlasDependencyGraphResult(project_path=str(root), nodes=sorted(nodes), edges=edges, skipped_files=skipped_files, warnings=warnings, metadata={"relative_path": request.relative_path, "max_files": request.max_files})

    def find_related_tests(self, request: AtlasRelatedTestsRequest) -> AtlasRelatedTestsResult:
        root = resolve_project_root(request.project_path)
        changed = [validate_relative_path(p) for p in request.changed_files]
        changed_paths = [ensure_under_project(root, root / p) for p in changed]
        all_files = [p for p in root.rglob('*') if p.is_file() and not any(part in _EXCLUDED_DIRS for part in p.parts)]
        tests = [p for p in all_files if _TEST_FILE_RE.search(p.relative_to(root).as_posix())]
        related: list[dict] = []
        seen: set[str] = set()

        def add_result(test_path: Path, reason: str, conf: str, matched: str):
            rel = test_path.relative_to(root).as_posix()
            if rel in seen or len(related) >= request.max_tests:
                return
            seen.add(rel)
            command_hint = ["python", "-m", "pytest", "-q", rel] if rel.endswith('.py') else ["command_id:node_test_runner", rel]
            related.append({"path": rel, "reason": reason, "confidence": conf, "matched_changed_file": matched, "command_hint": command_hint})

        for changed_rel, changed_path in zip(changed, changed_paths):
            stem = changed_path.stem
            for t in tests:
                trel = t.relative_to(root).as_posix()
                if trel in {f"tests/test_{stem}.py", f"tests/{stem}.test.ts", f"src/{stem}.test.ts"}:
                    add_result(t, "same-name test", "high", changed_rel)
            for t in tests:
                t_rel = t.relative_to(root)
                if len(t_rel.parts) > 1 and changed_path.parent.name in t_rel.parts:
                    add_result(t, "directory proximity", "medium", changed_rel)
            for t in tests:
                text, _ = self._read_text(t, 100000)
                if text and (stem in text or changed_path.with_suffix('').as_posix().replace('/', '.') in text):
                    add_result(t, "import/name match", "high", changed_rel)
            for t in tests:
                if stem.lower() in t.stem.lower():
                    add_result(t, "filename keyword match", "low", changed_rel)

        if not related:
            for t in tests[:request.max_tests]:
                add_result(t, "fallback representative tests", "low", "")

        confidence = "high" if any(r["confidence"] == "high" for r in related) else "medium" if any(r["confidence"] == "medium" for r in related) else "low"
        return AtlasRelatedTestsResult(project_path=str(root), changed_files=changed, related_tests=related[: request.max_tests], confidence=confidence, metadata={"test_file_count": len(tests)})
