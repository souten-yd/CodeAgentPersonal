"""Python semantic analyzer (PI-6).

AST-based real semantics: module/symbol/type graph, import & module resolution, alias and
re-export, inheritance/override, decorator relationships, and resolved vs candidate call
targets. Deterministic canonical refs (``py://<module>#<qualname>``) so identically named
symbols in different modules are never collapsed.

Pure stdlib (``ast``). Parse failures degrade gracefully with a diagnostic; the file node is
still emitted.
"""

from __future__ import annotations

import ast
from pathlib import Path

from agent.project_twin.analyzers.registry import AnalyzerCapability, AnalyzerOutput
from agent.project_twin.graph.semantic import SemanticEdge, SemanticNode

_VERSION = "py-sem-2.0"
_CAPS = frozenset({
    "modules", "symbols", "imports", "alias", "reexport",
    "inheritance", "override", "decorator", "calls_resolved", "calls_candidate",
})


def module_dotted(relpath: str) -> str:
    parts = Path(relpath).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _file_ref(relpath: str) -> str:
    return f"file://{Path(relpath).as_posix()}"


def _module_ref(dotted: str) -> str:
    return f"module://{dotted}"


def _sym_ref(module: str, qualname: str) -> str:
    return f"py://{module}#{qualname}"


class PythonAnalyzer:
    suffixes = (".py",)

    def capability(self) -> AnalyzerCapability:
        return AnalyzerCapability(language="python", version=_VERSION, capabilities=_CAPS)

    def analyze(self, root: Path, relpath: str, content: str) -> AnalyzerOutput:
        relposix = Path(relpath).as_posix()
        module = module_dotted(relpath)
        out = AnalyzerOutput()
        file_node = SemanticNode(ref=_file_ref(relpath), kind="file", name=Path(relpath).name,
                                 module=module, file=relposix)
        out.nodes.append(file_node)
        mod_node = SemanticNode(ref=_module_ref(module), kind="module", name=module,
                                module=module, file=relposix)
        out.nodes.append(mod_node)
        out.edges.append(SemanticEdge(file_node.ref, mod_node.ref, "contains", file=relposix))

        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            out.degraded = True
            out.diagnostics.append(f"python parse error in {relposix}: {exc}")
            return out

        is_init = Path(relpath).stem == "__init__"
        builder = _ModuleBuilder(module, relposix, is_init)
        builder.visit_module(tree)
        out.nodes.extend(builder.nodes)
        out.edges.extend(builder.edges)
        return out


class _ModuleBuilder:
    def __init__(self, module: str, relposix: str, is_init: bool) -> None:
        self.module = module
        self.file = relposix
        self.is_init = is_init
        self.nodes: list[SemanticNode] = []
        self.edges: list[SemanticEdge] = []
        # name -> imported target ref/info
        self.alias_to_target: dict[str, str] = {}     # alias name -> py://mod#sym or module://mod
        self.module_aliases: dict[str, str] = {}       # alias -> dotted module (for attr calls)
        self.local_defs: dict[str, str] = {}           # top-level name -> ref
        self.class_methods: dict[str, set[str]] = {}   # classname -> method names
        self.class_bases: dict[str, list[str]] = {}    # classname -> base name strings

    # -- pass 1: collect imports + top-level defs -----------------------------

    def visit_module(self, tree: ast.Module) -> None:
        for node in tree.body:
            self._collect_import(node)
            self._collect_def(node)
        # pass 2: emit symbols, inheritance, decorators, calls
        for node in tree.body:
            self._emit(node, parent_qual=None, parent_class=None)

    def _collect_import(self, node: ast.AST) -> None:
        mref = _module_ref(self.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _module_ref(alias.name)
                bound = alias.asname or alias.name.split(".")[0]
                self.module_aliases[bound] = alias.name
                self.alias_to_target[bound] = target
                self.nodes.append(SemanticNode(ref=f"import://{self.module}:{bound}", kind="import",
                                               name=bound, module=self.module, file=self.file,
                                               properties={"target": alias.name}))
                self.edges.append(SemanticEdge(mref, target, "imports", file=self.file))
                if alias.asname:
                    self.edges.append(SemanticEdge(f"import://{self.module}:{bound}", target,
                                                   "aliases", file=self.file))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # relative import: resolve against this package
                pkg = self.module if self.is_init else ".".join(self.module.split(".")[:-1])
                up = node.level - 1
                if up:
                    pkg = ".".join(pkg.split(".")[:-up]) if pkg else pkg
                base = f"{pkg}.{base}".strip(".") if base else pkg
            for alias in node.names:
                if alias.name == "*":
                    continue
                target = _sym_ref(base, alias.name)
                bound = alias.asname or alias.name
                self.alias_to_target[bound] = target
                self.edges.append(SemanticEdge(mref, target, "imports", file=self.file))
                if alias.asname:
                    self.nodes.append(SemanticNode(ref=f"import://{self.module}:{bound}", kind="import",
                                                   name=bound, module=self.module, file=self.file,
                                                   properties={"target": target}))
                    self.edges.append(SemanticEdge(f"import://{self.module}:{bound}", target,
                                                   "aliases", file=self.file))
                if self.is_init:
                    # __init__ re-exports the imported symbol.
                    self.edges.append(SemanticEdge(mref, target, "reexports", file=self.file))

    def _collect_def(self, node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.local_defs[node.name] = _sym_ref(self.module, node.name)
        elif isinstance(node, ast.ClassDef):
            self.local_defs[node.name] = _sym_ref(self.module, node.name)
            self.class_methods[node.name] = {
                b.name for b in node.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            self.class_bases[node.name] = [self._name_of(b) for b in node.bases if self._name_of(b)]

    # -- pass 2: emit ---------------------------------------------------------

    def _emit(self, node: ast.AST, parent_qual: str | None, parent_class: str | None) -> None:
        mref = _module_ref(self.module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{parent_qual}.{node.name}" if parent_qual else node.name
            kind = "method" if parent_class else "function"
            ref = _sym_ref(self.module, qual)
            self.nodes.append(SemanticNode(ref=ref, kind=kind, name=node.name, module=self.module,
                                           qualname=qual, file=self.file))
            self.edges.append(SemanticEdge(mref, ref, "defines", file=self.file))
            self._emit_decorators(node, ref)
            # override detection
            if parent_class:
                for base in self.class_bases.get(parent_class, []):
                    base_ref = self._resolve_name(base)
                    if base in self.class_methods and node.name in self.class_methods[base]:
                        self.edges.append(SemanticEdge(
                            ref, _sym_ref(self.module, f"{base}.{node.name}"), "overrides", file=self.file))
            self._emit_calls(node, ref, parent_class)
        elif isinstance(node, ast.ClassDef):
            qual = f"{parent_qual}.{node.name}" if parent_qual else node.name
            ref = _sym_ref(self.module, qual)
            self.nodes.append(SemanticNode(ref=ref, kind="class", name=node.name, module=self.module,
                                           qualname=qual, file=self.file))
            self.edges.append(SemanticEdge(mref, ref, "defines", file=self.file))
            self._emit_decorators(node, ref)
            for base in node.bases:
                bname = self._name_of(base)
                if not bname:
                    continue
                target, resolved = self._resolve_target(bname)
                self.edges.append(SemanticEdge(ref, target, "inherits", resolved=resolved,
                                               confidence=1.0 if resolved else 0.5, file=self.file))
                # Protocol/ABC heuristic -> implements
                if bname in ("Protocol", "ABC"):
                    self.edges.append(SemanticEdge(ref, target, "implements", resolved=resolved,
                                                   confidence=1.0 if resolved else 0.5, file=self.file))
            for b in node.body:
                self._emit(b, parent_qual=qual, parent_class=node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and parent_qual is None:
                    ref = _sym_ref(self.module, t.id)
                    self.nodes.append(SemanticNode(ref=ref, kind="variable", name=t.id,
                                                   module=self.module, qualname=t.id, file=self.file))
                    self.edges.append(SemanticEdge(mref, ref, "defines", file=self.file))

    def _emit_decorators(self, node, owner_ref: str) -> None:
        for dec in getattr(node, "decorator_list", []):
            dname = self._name_of(dec.func if isinstance(dec, ast.Call) else dec)
            if not dname:
                continue
            target, resolved = self._resolve_target(dname)
            self.edges.append(SemanticEdge(owner_ref, target, "decorates", resolved=resolved,
                                           confidence=1.0 if resolved else 0.5, file=self.file))

    def _emit_calls(self, func_node, owner_ref: str, parent_class: str | None) -> None:
        for sub in ast.walk(func_node):
            if not isinstance(sub, ast.Call):
                continue
            callee = sub.func
            if isinstance(callee, ast.Name):
                target, resolved = self._resolve_target(callee.id)
                self.edges.append(SemanticEdge(owner_ref, target, "calls", resolved=resolved,
                                               confidence=1.0 if resolved else 0.4, file=self.file))
            elif isinstance(callee, ast.Attribute):
                self._emit_attr_call(callee, owner_ref, parent_class)

    def _emit_attr_call(self, attr: ast.Attribute, owner_ref: str, parent_class: str | None) -> None:
        method = attr.attr
        base = attr.value
        if isinstance(base, ast.Name):
            # module.func() via imported module alias -> resolved into that module.
            if base.id in self.module_aliases:
                mod = self.module_aliases[base.id]
                self.edges.append(SemanticEdge(owner_ref, _sym_ref(mod, method), "calls",
                                               resolved=True, confidence=0.9, file=self.file))
                return
            # self.method() -> resolved within the current class when known.
            if base.id == "self" and parent_class and method in self.class_methods.get(parent_class, set()):
                self.edges.append(SemanticEdge(owner_ref, _sym_ref(self.module, f"{parent_class}.{method}"),
                                               "calls", resolved=True, confidence=0.95, file=self.file))
                return
        # Unknown receiver: a may-call candidate (not collapsed, low confidence).
        self.edges.append(SemanticEdge(owner_ref, f"pyname://{method}", "calls",
                                       resolved=False, confidence=0.3, file=self.file))

    # -- resolution helpers ---------------------------------------------------

    def _resolve_target(self, name: str) -> tuple[str, bool]:
        ref = self._resolve_name(name)
        if ref is not None:
            return ref, True
        return f"pyname://{name}", False

    def _resolve_name(self, name: str) -> str | None:
        if name in self.local_defs:
            return self.local_defs[name]
        if name in self.alias_to_target:
            return self.alias_to_target[name]
        return None

    @staticmethod
    def _name_of(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""
