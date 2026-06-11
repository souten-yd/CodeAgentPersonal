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


class _PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.current_class: list[str] = []
        self.symbols: list[AtlasSymbol] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        parent = self.current_class[-1] if self.current_class else ''
        self.symbols.append(AtlasSymbol(name=node.name, kind='class', file_path=self.rel, line=node.lineno, column=node.col_offset, parent=parent))
        self.current_class.append(node.name)
        self.generic_visit(node)
        self.current_class.pop()

    def _add_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        parent = self.current_class[-1] if self.current_class else ''
        kind = 'method' if parent else 'function'
        sig = f"{node.name}({', '.join(arg.arg for arg in node.args.args)})"
        self.symbols.append(AtlasSymbol(name=node.name, kind=kind, file_path=self.rel, line=node.lineno, column=node.col_offset, parent=parent, signature=sig))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._add_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._add_function(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.symbols.append(AtlasSymbol(name=alias.name, kind='import', file_path=self.rel, line=node.lineno, column=node.col_offset))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ''
        for alias in node.names:
            self.symbols.append(AtlasSymbol(name=f"{mod}.{alias.name}".strip('.'), kind='import', file_path=self.rel, line=node.lineno, column=node.col_offset))


class AtlasCodeIntelService:
    def _iter_files(self, root: Path, relative_path: str, max_files: int):
        base = root if not relative_path else ensure_under_project(root, root / validate_relative_path(relative_path))
        if relative_path and not base.exists():
            raise ValueError(f'path_not_found: {relative_path}')
        out = []
        if base.is_file():
            return [base]
        for path in base.rglob('*'):
            if any(part in _EXCLUDED_DIRS for part in path.parts):
                continue
            if path.is_file():
                out.append(path)
                if len(out) >= max_files:
                    break
        return out

    def _read_text(self, path: Path, max_bytes: int):
        try:
            data = path.read_bytes()
        except (PermissionError, OSError) as exc:
            return None, f'read error: {exc.__class__.__name__}'
        if b"\x00" in data:
            return None, 'binary file skipped'
        if len(data) > max_bytes:
            return None, 'large file skipped'
        try:
            return data.decode('utf-8'), ''
        except UnicodeDecodeError:
            return None, 'read error: UnicodeDecodeError'

    def _resolve_target(self, root: Path, source_rel: str, target: str, kind: str):
        source_dir = (root / source_rel).parent
        if kind == 'python_import':
            if target.startswith('.'):
                candidate = ensure_under_project(root, source_dir / (target.lstrip('.') + '.py'))
                if candidate.exists():
                    return candidate.relative_to(root).as_posix(), 'resolved'
                return '', 'unresolved'
            mod_path = Path(*target.split('.')) if target else Path('')
            for candidate in (root / f'{mod_path}.py', root / mod_path / '__init__.py'):
                if candidate.exists() and ensure_under_project(root, candidate):
                    return candidate.relative_to(root).as_posix(), 'resolved'
            return '', 'external' if target and not target.startswith('.') else 'unresolved'
        if kind in {'js_import', 'html_script', 'html_stylesheet', 'css_import'}:
            if not target.startswith(('./', '../')):
                if kind in {'html_script', 'html_stylesheet', 'css_import'} and not target.startswith(('/', 'http://', 'https://')):
                    rel_candidate = ensure_under_project(root, source_dir / target)
                    if rel_candidate.exists() and rel_candidate.is_file():
                        return rel_candidate.relative_to(root).as_posix(), 'resolved'
                return '', 'external'
            raw = ensure_under_project(root, source_dir / target)
            candidates = [raw]
            if raw.suffix == '':
                candidates += [raw.with_suffix('.js'), raw.with_suffix('.ts'), raw / 'index.js', raw / 'index.ts']
            for candidate in candidates:
                if candidate.exists() and candidate.is_file() and ensure_under_project(root, candidate):
                    return candidate.relative_to(root).as_posix(), 'resolved'
            return '', 'unresolved'
        return '', 'unresolved'

    def build_symbol_index(self, request: AtlasSymbolIndexRequest) -> AtlasSymbolIndexResult:
        root = resolve_project_root(request.project_path)
        symbols: list[AtlasSymbol] = []
        skipped_files: list[dict] = []
        warnings: list[str] = []
        files = self._iter_files(root, request.relative_path, request.max_files)
        scanned_file_count = 0
        truncated = False
        for path in files:
            scanned_file_count += 1
            rel = path.relative_to(root).as_posix()
            text, skip_reason = self._read_text(path, request.max_bytes_per_file)
            if text is None:
                skipped_files.append({'path': rel, 'reason': skip_reason})
                continue
            ext = path.suffix.lower()
            try:
                if ext == '.py':
                    tree = ast.parse(text)
                    v = _PythonSymbolVisitor(rel)
                    v.visit(tree)
                    symbols.extend(v.symbols)
                elif ext in {'.js', '.ts', '.jsx', '.tsx'}:
                    for idx, line in enumerate(text.splitlines(), start=1):
                        for m in re.finditer(r"^\s*import\s+.+?from\s+['\"]([^'\"]+)['\"]", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind='import', file_path=rel, line=idx, column=m.start(1)))
                        for m in re.finditer(r"^\s*export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*([A-Za-z_$][\w$]*)?", line):
                            if m.group(1):
                                symbols.append(AtlasSymbol(name=m.group(1), kind='export', file_path=rel, line=idx, column=m.start(1)))
                elif ext == '.html':
                    for idx, line in enumerate(text.splitlines(), start=1):
                        for m in re.finditer(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", line):
                            symbols.append(AtlasSymbol(name=m.group(1), kind='html_id', file_path=rel, line=idx, column=m.start(1)))
                elif ext == '.css':
                    for idx, line in enumerate(text.splitlines(), start=1):
                        for m in re.finditer(r"^\s*([^{@][^{]+)\{", line):
                            symbols.append(AtlasSymbol(name=m.group(1).strip(), kind='css_selector', file_path=rel, line=idx, column=m.start(1)))
            except SyntaxError:
                skipped_files.append({'path': rel, 'reason': 'syntax error'})
                warnings.append(f'syntax error skipped: {rel}')
            if len(symbols) >= request.max_symbols:
                symbols = symbols[:request.max_symbols]
                warnings.append('max_symbols limit reached')
                truncated = True
                break
        if len(files) >= request.max_files:
            warnings.append('max_files limit reached')
        return AtlasSymbolIndexResult(project_path=str(root), symbols=symbols, file_count=len(files), skipped_files=skipped_files, warnings=warnings, metadata={'relative_path': request.relative_path, 'truncated': truncated, 'max_files': request.max_files, 'max_symbols': request.max_symbols, 'scanned_file_count': scanned_file_count, 'returned_symbol_count': len(symbols), 'skipped_file_count': len(skipped_files)})

    def build_dependency_graph(self, request: AtlasDependencyGraphRequest) -> AtlasDependencyGraphResult:
        root = resolve_project_root(request.project_path)
        files = self._iter_files(root, request.relative_path, request.max_files)
        nodes: set[str] = set()
        edges: list[AtlasDependencyEdge] = []
        skipped_files: list[dict] = []
        warnings: list[str] = []
        scanned_file_count = 0
        truncated = False
        for path in files:
            scanned_file_count += 1
            rel = path.relative_to(root).as_posix()
            nodes.add(rel)
            text, skip_reason = self._read_text(path, request.max_bytes_per_file)
            if text is None:
                skipped_files.append({'path': rel, 'reason': skip_reason})
                continue
            ext = path.suffix.lower()
            for idx, line in enumerate(text.splitlines(), start=1):
                if ext == '.py':
                    for m in re.finditer(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", line):
                        tgt = m.group(1) or m.group(2)
                        resolved, resolution = self._resolve_target(root, rel, tgt, 'python_import')
                        edges.append(AtlasDependencyEdge(source=rel, target=tgt, kind='python_import', line=idx, metadata={'raw_target': tgt, 'resolved_target_path': resolved, 'resolution': resolution}))
                elif ext in {'.js', '.ts', '.jsx', '.tsx'}:
                    for m in re.finditer(r"import\s+.+?from\s+['\"]([^'\"]+)['\"]", line):
                        tgt = m.group(1)
                        resolved, resolution = self._resolve_target(root, rel, tgt, 'js_import')
                        edges.append(AtlasDependencyEdge(source=rel, target=tgt, kind='js_import', line=idx, metadata={'raw_target': tgt, 'resolved_target_path': resolved, 'resolution': resolution}))
                elif ext == '.html':
                    for m in re.finditer(r"<script[^>]*\bsrc=['\"]([^'\"]+)['\"]", line):
                        tgt = m.group(1)
                        resolved, resolution = self._resolve_target(root, rel, tgt, 'html_script')
                        edges.append(AtlasDependencyEdge(source=rel, target=tgt, kind='html_script', line=idx, metadata={'raw_target': tgt, 'resolved_target_path': resolved, 'resolution': resolution}))
                    for m in re.finditer(r"<link[^>]*\brel=['\"]stylesheet['\"][^>]*\bhref=['\"]([^'\"]+)['\"]", line):
                        tgt = m.group(1)
                        resolved, resolution = self._resolve_target(root, rel, tgt, 'html_stylesheet')
                        edges.append(AtlasDependencyEdge(source=rel, target=tgt, kind='html_stylesheet', line=idx, metadata={'raw_target': tgt, 'resolved_target_path': resolved, 'resolution': resolution}))
                elif ext == '.css':
                    for m in re.finditer(r"@import\s+(?:url\()?['\"]([^'\"]+)['\"]", line):
                        tgt = m.group(1)
                        resolved, resolution = self._resolve_target(root, rel, tgt, 'css_import')
                        edges.append(AtlasDependencyEdge(source=rel, target=tgt, kind='css_import', line=idx, metadata={'raw_target': tgt, 'resolved_target_path': resolved, 'resolution': resolution}))
            if len(edges) >= request.max_edges:
                edges = edges[:request.max_edges]
                warnings.append('max_edges limit reached')
                truncated = True
                break
        nodes.update(edge.target for edge in edges)
        if len(files) >= request.max_files:
            warnings.append('max_files limit reached')
        return AtlasDependencyGraphResult(project_path=str(root), nodes=sorted(nodes), edges=edges, skipped_files=skipped_files, warnings=warnings, metadata={'relative_path': request.relative_path, 'truncated': truncated, 'max_files': request.max_files, 'max_edges': request.max_edges, 'scanned_file_count': scanned_file_count, 'returned_edge_count': len(edges), 'skipped_file_count': len(skipped_files)})

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
            verification_hint = {'command_id': 'pytest_selected' if rel.endswith('.py') else '', 'test_path': rel, 'test_file': rel, 'note': 'allowlist compatible' if rel.endswith('.py') else 'manual selection required; JS test runner allowlist is not configured yet'}
            related.append({'path': rel, 'reason': reason, 'confidence': conf, 'matched_changed_file': matched, 'verification_hint': verification_hint})

        for changed_rel, changed_path in zip(changed, changed_paths):
            stem = changed_path.stem
            for t in tests:
                trel = t.relative_to(root).as_posix()
                if trel in {f'tests/test_{stem}.py', f'tests/{stem}.test.ts', f'src/{stem}.test.ts'}:
                    add_result(t, 'same-name test', 'high', changed_rel)
            for t in tests:
                t_rel = t.relative_to(root)
                if len(t_rel.parts) > 1 and changed_path.parent.name in t_rel.parts:
                    add_result(t, 'directory proximity', 'medium', changed_rel)
            for t in tests:
                text, _ = self._read_text(t, 100000)
                if text and (stem in text or changed_path.with_suffix('').as_posix().replace('/', '.') in text):
                    add_result(t, 'import/name match', 'high', changed_rel)
            for t in tests:
                if stem.lower() in t.stem.lower():
                    add_result(t, 'filename keyword match', 'low', changed_rel)

        if not related:
            for t in tests[:request.max_tests]:
                add_result(t, 'fallback representative tests', 'low', '')

        confidence = 'high' if any(r['confidence'] == 'high' for r in related) else 'medium' if any(r['confidence'] == 'medium' for r in related) else 'low'
        related_files = self._related_files_from_dependencies(root, changed, max_files=25)
        return AtlasRelatedTestsResult(
            project_path=str(root),
            changed_files=changed,
            related_tests=related[: request.max_tests],
            confidence=confidence,
            metadata={
                'test_file_count': len(tests),
                'related_files': related_files,
                'related_file_count': len(related_files),
            },
        )

    def _related_files_from_dependencies(self, root: Path, changed: list[str], *, max_files: int) -> list[dict]:
        if not changed:
            return []
        try:
            graph = self.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(root), max_files=2000))
        except Exception:
            return []
        changed_set = set(changed)
        scores: dict[str, dict] = {}

        def add(path: str, *, score: int, reason: str, via: str):
            if not path or path in changed_set:
                return
            rec = scores.setdefault(path, {'path': path, 'score': 0, 'reasons': [], 'via': []})
            rec['score'] += score
            if reason not in rec['reasons']:
                rec['reasons'].append(reason)
            if via and via not in rec['via']:
                rec['via'].append(via)

        for edge in graph.edges:
            resolved = str((edge.metadata or {}).get('resolved_target_path') or '')
            target = resolved or str(edge.target or '')
            source = str(edge.source or '')
            if source in changed_set:
                add(target, score=3 if resolved else 1, reason='outgoing_dependency', via=source)
            if target in changed_set or resolved in changed_set:
                add(source, score=4, reason='incoming_dependency', via=target or resolved)
        for rel in changed:
            base = (root / rel).parent
            if not base.exists():
                continue
            for neighbor in base.glob('*'):
                if not neighbor.is_file():
                    continue
                nrel = neighbor.relative_to(root).as_posix()
                if nrel not in changed_set:
                    add(nrel, score=1, reason='directory_neighbor', via=rel)
        return sorted(scores.values(), key=lambda r: (-int(r.get('score') or 0), str(r.get('path') or '')))[:max_files]


class ProjectIntelligenceCodeIntelAdapter(AtlasCodeIntelService):
    """Compatibility adapter for read-only Atlas code-intelligence consumers."""
