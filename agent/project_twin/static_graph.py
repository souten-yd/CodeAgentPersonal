"""Deterministic static structural analyzer (PDT-3).

Projects repository structure and static semantics into typed twin nodes/edges:
- repository / directory / file / module / package nodes;
- Python class / function / method nodes;
- import, inheritance and (name-based) call edges;
- FastAPI route projection;
- test and pytest-fixture nodes;
- HTML <script>/<link>/<style> asset links;
- basic JS import and event-handler links.

This module is pure: it reads files and returns a `StaticAnalysisResult` (a `TwinDelta`
plus diagnostics). It has no store dependency and never mutates anything. Canonical refs
are stable strings; node ids are a deterministic hash of the canonical ref so edges can
reference targets without the target object being present in the same delta.
"""

from __future__ import annotations

import ast
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from agent.project_twin.contracts import (
    StaticAnalysisRequest,
    StaticAnalysisResult,
    TwinDelta,
    TwinEdge,
    TwinNode,
)

PARSER_VERSION = "static_graph.v3"

_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", "venv_sys", "tts_envs", "third_party",
    "ca_data", ".pytest_cache", "assets", "dist", "build", ".mypy_cache",
}
_MAX_FILE_BYTES = 400_000


def nid(canonical_ref: str) -> str:
    """Deterministic node id from a canonical ref."""

    return hashlib.sha1(canonical_ref.encode("utf-8")).hexdigest()[:16]


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def _module_dotted(rel_path: str) -> str:
    stem = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    parts = [s for s in stem.split("/") if s]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_test_file(rel_path: str) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py") or name.endswith("_test.py")


# Common builtins/keywords-as-calls we never treat as an ambiguous *project* call (avoids diagnostic
# noise). Not exhaustive — only the high-frequency names that would otherwise dominate diagnostics.
_PY_BUILTINS = frozenset({
    "len", "print", "open", "str", "int", "float", "bool", "bytes", "dict", "list", "set", "tuple",
    "range", "enumerate", "zip", "map", "filter", "sorted", "reversed", "sum", "min", "max", "abs",
    "isinstance", "issubclass", "super", "getattr", "setattr", "hasattr", "delattr", "type", "repr",
    "format", "vars", "dir", "id", "hash", "iter", "next", "any", "all", "round", "callable",
})


def _build_module_map(root: Path) -> dict[str, str]:
    """Map a project module's dotted path -> its rel file path, for import resolution."""
    out: dict[str, str] = {}
    for p in _iter_files(root, None):
        if p.suffix == ".py":
            rel = _rel(root, p)
            out.setdefault(_module_dotted(rel), rel)
    return out


def _import_table(tree: ast.Module) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """(module_aliases, from_imports) for a module.

    module_aliases: local name -> dotted module (`import a.b as x` -> {x: a.b}; `import a.b` -> {a: a}).
    from_imports:   local name -> (dotted module, original symbol) for absolute `from m import f [as g]`.
    Relative and star imports are skipped (left to name-based matching).
    """
    module_aliases: dict[str, str] = {}
    from_imports: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    module_aliases[alias.asname] = alias.name
                else:
                    module_aliases.setdefault(alias.name.split(".")[0], alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            mod = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                from_imports[alias.asname or alias.name] = (mod, alias.name)
    return module_aliases, from_imports


def _attr_chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return list(reversed(parts))
    return None


def _resolve_name_call(name, from_imports, local_funcs, module_map, rel) -> tuple[str | None, str | None]:
    if name in from_imports:
        mod, orig = from_imports[name]
        if mod in module_map:
            return f"py://{module_map[mod]}#{orig}", "from_import"
    if name in local_funcs:
        return f"py://{rel}#{local_funcs[name]}", "local"
    return None, None


def _resolve_attr_call(chain, module_aliases, module_map) -> tuple[str | None, str | None]:
    func = chain[-1]
    prefix = chain[:-1]
    candidates = [".".join(prefix)]
    if prefix and prefix[0] in module_aliases:
        candidates.append(".".join([module_aliases[prefix[0]]] + prefix[1:]))
    for mod in candidates:
        if mod in module_map:
            return f"py://{module_map[mod]}#{func}", "alias_import"
    return None, None


class _Builder:
    """Accumulates nodes/edges/diagnostics for one analysis run."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.now = datetime.now(timezone.utc)
        self.nodes: list[TwinNode] = []
        self.edges: list[TwinEdge] = []
        self.diagnostics: list[dict] = []
        self._seen_nodes: set[str] = set()
        self._seen_edges: set[str] = set()

    def node(
        self,
        *,
        domain: str,
        node_type: str,
        canonical_ref: str,
        label: str,
        source_ref: str,
        derivation: str = "deterministic_static",
        confidence: float = 1.0,
        properties: dict | None = None,
    ) -> str:
        node_id = nid(canonical_ref)
        if canonical_ref in self._seen_nodes:
            return node_id
        self._seen_nodes.add(canonical_ref)
        self.nodes.append(
            TwinNode(
                node_id=node_id,
                project_id=self.project_id,
                domain=domain,
                node_type=node_type,
                canonical_ref=canonical_ref,
                label=label,
                properties=properties or {},
                source_kind="git",
                source_ref=source_ref,
                derivation=derivation,
                confidence=confidence,
                status="declared",
                valid_from=self.now,
                created_at=self.now,
                updated_at=self.now,
            )
        )
        return node_id

    def edge(
        self,
        *,
        domain: str,
        edge_type: str,
        source_ref_node: str,
        target_ref_node: str,
        source_ref: str,
        derivation: str = "deterministic_static",
        confidence: float = 1.0,
        properties: dict | None = None,
    ) -> None:
        edge_id = nid(f"{edge_type}|{source_ref_node}|{target_ref_node}")
        key = edge_id
        if key in self._seen_edges:
            return
        self._seen_edges.add(key)
        self.edges.append(
            TwinEdge(
                edge_id=edge_id,
                project_id=self.project_id,
                domain=domain,
                source_node_id=nid(source_ref_node),
                target_node_id=nid(target_ref_node),
                edge_type=edge_type,
                properties=dict(properties or {}),
                source_kind="git",
                source_ref=source_ref,
                derivation=derivation,
                confidence=confidence,
                status="declared",
                valid_from=self.now,
                created_at=self.now,
                updated_at=self.now,
            )
        )


def _iter_files(root: Path, changed: list[str] | None) -> list[Path]:
    if changed:
        out = []
        for rel in sorted(set(changed)):
            p = root / rel
            if p.is_file():
                out.append(p)
        return out
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        parts = set(p.relative_to(root).parts)
        if parts & _IGNORE_DIRS:
            continue
        if p.suffix in {".py", ".html", ".js"}:
            files.append(p)
    return files


def _decorator_name(dec: ast.expr) -> str:
    # @app.get -> "app.get" ; @pytest.fixture -> "pytest.fixture" ; @fixture -> "fixture"
    target = dec.func if isinstance(dec, ast.Call) else dec
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


def _route_path(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Call) and dec.args:
        first = dec.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def _analyze_python(b: _Builder, root: Path, path: Path, file_ref: str, module_map: dict[str, str] | None = None) -> None:
    rel = _rel(root, path)
    module_map = module_map or {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except SyntaxError as exc:
        b.diagnostics.append({"code": "parse_error", "file": rel, "detail": str(exc)})
        return
    except OSError as exc:
        b.diagnostics.append({"code": "read_error", "file": rel, "detail": str(exc)})
        return

    module_ref = f"module://{_module_dotted(rel)}"
    module_node = b.node(domain="structural", node_type="module", canonical_ref=module_ref, label=_module_dotted(rel), source_ref=rel)
    b.edge(domain="structural", edge_type="contains", source_ref_node=file_ref, target_ref_node=module_ref, source_ref=rel)

    is_test = _is_test_file(rel)
    # Import-aware call resolution: alias/from-import tables + this file's top-level function names +
    # per-class method names (so `self.m()` resolves to the concrete method on the same class).
    module_aliases, from_imports = _import_table(tree)
    local_funcs = {n.name: n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    class_methods: dict[str, set[str]] = {
        node.name: {it.name for it in node.body if isinstance(it, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in tree.body if isinstance(node, ast.ClassDef)
    }

    def handle_function(fn: ast.FunctionDef | ast.AsyncFunctionDef, qual: str, container_ref: str) -> None:
        sym_ref = f"py://{rel}#{qual}"
        node_type = "method" if "." in qual else "function"
        b.node(domain="structural", node_type=node_type, canonical_ref=sym_ref, label=qual, source_ref=rel,
               properties={
                   "async": isinstance(fn, ast.AsyncFunctionDef),
                   "start_line": getattr(fn, "lineno", 1),
                   "end_line": getattr(fn, "end_lineno", getattr(fn, "lineno", 1)),
               })
        b.edge(domain="structural", edge_type="defines", source_ref_node=container_ref, target_ref_node=sym_ref, source_ref=rel)

        for dec in fn.decorator_list:
            dname = _decorator_name(dec)
            tail = dname.rsplit(".", 1)[-1]
            # FastAPI route projection
            if tail in _HTTP_METHODS and ("app" in dname or "router" in dname):
                rpath = _route_path(dec)
                if rpath:
                    route_ref = f"route://{tail.upper()} {rpath}"
                    b.node(domain="structural", node_type="api_route", canonical_ref=route_ref,
                           label=f"{tail.upper()} {rpath}", source_ref=rel,
                           properties={
                               "start_line": getattr(fn, "lineno", 1),
                               "end_line": getattr(fn, "end_lineno", getattr(fn, "lineno", 1)),
                           })
                    b.edge(domain="structural", edge_type="handled_by", source_ref_node=route_ref, target_ref_node=sym_ref, source_ref=rel)
            # pytest fixture
            if tail == "fixture" and ("pytest" in dname or dname == "fixture"):
                fx_ref = f"fixture://{rel}::{qual}"
                b.node(domain="structural", node_type="fixture", canonical_ref=fx_ref, label=qual, source_ref=rel)
                b.edge(domain="structural", edge_type="provides_fixture", source_ref_node=sym_ref, target_ref_node=fx_ref, source_ref=rel)

        if is_test and qual.rsplit(".", 1)[-1].startswith("test_"):
            test_ref = f"test://{rel}::{qual}"
            b.node(domain="structural", node_type="test", canonical_ref=test_ref, label=qual, source_ref=rel)
            b.edge(domain="structural", edge_type="covers_symbol", source_ref_node=test_ref, target_ref_node=sym_ref, source_ref=rel)

        # name-based call edges
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call):
                callee = sub.func
                callee_name = None
                resolved_ref = None
                resolution = None
                is_attr = False
                if isinstance(callee, ast.Name):
                    callee_name = callee.id
                    resolved_ref, resolution = _resolve_name_call(callee_name, from_imports, local_funcs, module_map, rel)
                elif isinstance(callee, ast.Attribute):
                    callee_name = callee.attr
                    is_attr = True
                    # self.method() inside a class -> resolve to the concrete method on this class.
                    if (isinstance(callee.value, ast.Name) and callee.value.id == "self" and "." in qual
                            and callee.attr in class_methods.get(qual.split(".")[0], set())):
                        resolved_ref, resolution = f"py://{rel}#{qual.split('.')[0]}.{callee.attr}", "self_method"
                    if resolved_ref is None:
                        chain = _attr_chain(callee)
                        if chain and len(chain) >= 2:
                            resolved_ref, resolution = _resolve_attr_call(chain, module_aliases, module_map)
                if callee_name:
                    # Always keep the name-based edge so a caller matchable only by name is still linked.
                    b.edge(domain="structural", edge_type="calls", source_ref_node=sym_ref,
                           target_ref_node=f"pyname://{callee_name}", source_ref=rel,
                           confidence=0.7)
                    if resolved_ref:
                        # Import/alias/local resolution to a stable canonical ref — higher confidence
                        # than the name-only edge.
                        b.edge(domain="structural", edge_type="calls", source_ref_node=sym_ref,
                               target_ref_node=resolved_ref, source_ref=rel, confidence=0.9,
                               properties={"resolution": resolution})
                    elif not is_attr and callee_name not in _PY_BUILTINS:
                        # A bare-name project-looking call we could not resolve to a canonical ref:
                        # retained name-based above, flagged here so the imprecision is visible.
                        b.diagnostics.append({"code": "ambiguous_call", "file": rel, "caller": qual, "callee": callee_name})

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls_ref = f"py://{rel}#{node.name}"
            b.node(
                domain="structural",
                node_type="class",
                canonical_ref=cls_ref,
                label=node.name,
                source_ref=rel,
                properties={
                    "start_line": getattr(node, "lineno", 1),
                    "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                },
            )
            b.edge(domain="structural", edge_type="defines", source_ref_node=module_ref, target_ref_node=cls_ref, source_ref=rel)
            for base in node.bases:
                base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
                if base_name:
                    b.edge(domain="structural", edge_type="inherits", source_ref_node=cls_ref,
                           target_ref_node=f"pyname://{base_name}", source_ref=rel, confidence=0.9)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    handle_function(item, f"{node.name}.{item.name}", cls_ref)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            handle_function(node, node.name, module_ref)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                b.edge(domain="structural", edge_type="imports", source_ref_node=module_ref,
                       target_ref_node=f"module://{alias.name}", source_ref=rel)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                b.edge(domain="structural", edge_type="imports", source_ref_node=module_ref,
                       target_ref_node=f"module://{node.module}", source_ref=rel)


_HTML_SCRIPT = re.compile(r"""<script[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_HTML_LINK = re.compile(r"""<link[^>]*\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_HTML_INLINE = re.compile(r"<(script|style)(?![^>]*\bsrc)[^>]*>", re.IGNORECASE)


def _analyze_html(b: _Builder, root: Path, path: Path, file_ref: str) -> None:
    rel = _rel(root, path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        b.diagnostics.append({"code": "read_error", "file": rel, "detail": str(exc)})
        return
    for src in _HTML_SCRIPT.findall(text):
        asset_ref = f"asset://{src}"
        b.node(domain="structural", node_type="asset", canonical_ref=asset_ref, label=src, source_ref=rel, confidence=0.9)
        b.edge(domain="structural", edge_type="loads_script", source_ref_node=file_ref, target_ref_node=asset_ref, source_ref=rel, confidence=0.9)
    for href in _HTML_LINK.findall(text):
        asset_ref = f"asset://{href}"
        b.node(domain="structural", node_type="asset", canonical_ref=asset_ref, label=href, source_ref=rel, confidence=0.9)
        b.edge(domain="structural", edge_type="links_asset", source_ref_node=file_ref, target_ref_node=asset_ref, source_ref=rel, confidence=0.9)
    inline = len(_HTML_INLINE.findall(text))
    if inline:
        b.node(domain="structural", node_type="inline_block", canonical_ref=f"asset://{rel}#inline",
               label=f"{inline} inline block(s)", source_ref=rel, derivation="heuristic_static", confidence=0.6,
               properties={"count": inline})
        b.edge(domain="structural", edge_type="contains_inline", source_ref_node=file_ref,
               target_ref_node=f"asset://{rel}#inline", source_ref=rel, derivation="heuristic_static", confidence=0.6)


_JS_IMPORT = re.compile(r"""\bimport\b[^;]*?["']([^"']+)["']""")
_JS_REQUIRE = re.compile(r"""\brequire\s*\(\s*["']([^"']+)["']\s*\)""")
_JS_ADDLISTENER = re.compile(r"""addEventListener\s*\(\s*["']([a-zA-Z]+)["']""")


def _analyze_js(b: _Builder, root: Path, path: Path, file_ref: str) -> None:
    rel = _rel(root, path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        b.diagnostics.append({"code": "read_error", "file": rel, "detail": str(exc)})
        return
    for spec in set(_JS_IMPORT.findall(text)) | set(_JS_REQUIRE.findall(text)):
        b.edge(domain="structural", edge_type="imports", source_ref_node=file_ref,
               target_ref_node=f"jsmodule://{spec}", source_ref=rel, derivation="heuristic_static", confidence=0.7)
    for event in sorted(set(_JS_ADDLISTENER.findall(text))):
        handler_ref = f"event://{rel}#{event}"
        b.node(domain="behavioral", node_type="event_handler", canonical_ref=handler_ref, label=f"on:{event}",
               source_ref=rel, derivation="heuristic_static", confidence=0.5)
        b.edge(domain="behavioral", edge_type="handles_event", source_ref_node=file_ref, target_ref_node=handler_ref,
               source_ref=rel, derivation="heuristic_static", confidence=0.5)


class StaticStructuralAnalyzer:
    """Pure `StaticAnalysisPort` implementation."""

    def analyze(self, request: StaticAnalysisRequest) -> StaticAnalysisResult:
        root = Path(request.project_path)
        b = _Builder(request.project_id)

        if not root.is_dir():
            b.diagnostics.append({"code": "project_path_missing", "detail": request.project_path})
            return self._result(request, b)

        repo_ref = "repo://"
        b.node(domain="structural", node_type="repository", canonical_ref=repo_ref, label=root.name, source_ref=".")

        changed = None if request.full_rebuild else (request.changed_paths or None)
        files = _iter_files(root, changed)
        # Full project module map (all py files, not just the changed subset) so import-based call
        # resolution stays correct during incremental rebuilds.
        module_map = _build_module_map(root)

        seen_dirs: set[str] = set()
        for path in files:
            if path.stat().st_size > _MAX_FILE_BYTES and path.suffix != ".py":
                b.diagnostics.append({"code": "skipped_large_file", "file": _rel(root, path)})
                continue
            rel = _rel(root, path)
            file_ref = f"file://{rel}"
            b.node(domain="structural", node_type="file", canonical_ref=file_ref, label=rel, source_ref=rel)
            # directory containment chain
            parent_rel = rel.rsplit("/", 1)[0] if "/" in rel else ""
            parent_ref = f"dir://{parent_rel}" if parent_rel else repo_ref
            if parent_rel and parent_rel not in seen_dirs:
                seen_dirs.add(parent_rel)
                b.node(domain="structural", node_type="directory", canonical_ref=parent_ref, label=parent_rel, source_ref=parent_rel)
                b.edge(domain="structural", edge_type="contains", source_ref_node=repo_ref, target_ref_node=parent_ref, source_ref=parent_rel)
            b.edge(domain="structural", edge_type="contains", source_ref_node=parent_ref, target_ref_node=file_ref, source_ref=rel)

            if path.suffix == ".py":
                _analyze_python(b, root, path, file_ref, module_map)
            elif path.suffix == ".html":
                _analyze_html(b, root, path, file_ref)
            elif path.suffix == ".js":
                _analyze_js(b, root, path, file_ref)

        return self._result(request, b)

    @staticmethod
    def _result(request: StaticAnalysisRequest, b: _Builder) -> StaticAnalysisResult:
        delta = TwinDelta(
            project_id=request.project_id,
            base_revision_id=request.base_revision_id,
            idempotency_key=f"static:{PARSER_VERSION}:{','.join(sorted(request.changed_paths)) or 'full'}:{b.now.isoformat()}",
            trigger_type="static_analysis",
            trigger_ref=PARSER_VERSION,
            nodes=b.nodes,
            edges=b.edges,
            diagnostics=b.diagnostics,
        )
        return StaticAnalysisResult(
            project_id=request.project_id,
            delta=delta,
            parser_versions={"static_graph": PARSER_VERSION},
            diagnostics=b.diagnostics,
        )
