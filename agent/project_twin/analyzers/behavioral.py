"""Behavioral analyzer (PI-7).

Infers behavioral facts (control flow, concrete side effects, API routes, state mutation,
events, retry/recovery, UI event -> API) on top of the PI-6 static semantic identities.
Every fact is inferred with a derivation and confidence < 1.0; heuristics never become
verified here. Unsupported constructs emit diagnostics rather than fabricated certainty.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from agent.project_twin.analyzers.python import module_dotted
from agent.project_twin.graph.behavioral import (
    BehaviorFact,
    BehaviorRelation,
    BehavioralGraph,
)
from agent.project_twin.graph.semantic import SemanticGraph

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
_DB_METHODS = {"execute", "executemany", "executescript", "query", "fetchone", "fetchall", "commit"}
_NET_MODULES = {"requests", "httpx", "urllib", "aiohttp", "socket"}
_PROC = {"subprocess", "popen", "system"}
_ROLLBACK_NAMES = {"rollback", "abort", "revert", "undo", "compensate"}

_SQL_TABLE = re.compile(r"\b(?:from|into|update|join)\s+([A-Za-z_][\w]*)", re.I)
_SYM_REF = "py://{module}#{qual}"


def _sym(module: str, qual: str) -> str:
    return _SYM_REF.format(module=module, qual=qual)


class BehavioralAnalyzer:
    """Produces a BehavioralGraph from source, reusing static refs as owners."""

    def analyze_project(self, files: dict[str, str], *, behavioral: BehavioralGraph | None = None) -> tuple[BehavioralGraph, list[str]]:
        graph = behavioral or BehavioralGraph()
        diagnostics: list[str] = []
        for relpath in sorted(files):
            graph.invalidate_file(Path(relpath).as_posix())
            suffix = Path(relpath).suffix.lower()
            if suffix == ".py":
                self._analyze_python(graph, relpath, files[relpath], diagnostics)
            elif suffix in (".js", ".jsx", ".ts", ".tsx", ".vue"):
                self._analyze_js(graph, relpath, files[relpath], diagnostics)
        return graph, diagnostics

    # -- Python ---------------------------------------------------------------

    def _analyze_python(self, graph: BehavioralGraph, relpath: str, content: str, diags: list[str]) -> None:
        relposix = Path(relpath).as_posix()
        module = module_dotted(relpath)
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            diags.append(f"behavioral: python parse error in {relposix}: {exc}")
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._py_function(graph, module, relposix, node, tree)

    def _py_function(self, graph, module, relposix, fn, tree) -> None:
        qual = self._qualname(tree, fn)
        owner = _sym(module, qual)

        # control flow summary
        flags = {"branches": 0, "loops": 0, "returns": 0, "raises": 0,
                 "has_try": False, "has_finally": False, "awaits": 0}
        for sub in ast.walk(fn):
            if isinstance(sub, ast.If):
                flags["branches"] += 1
            elif isinstance(sub, (ast.For, ast.While, ast.AsyncFor)):
                flags["loops"] += 1
            elif isinstance(sub, ast.Return):
                flags["returns"] += 1
            elif isinstance(sub, ast.Raise):
                flags["raises"] += 1
            elif isinstance(sub, ast.Try):
                flags["has_try"] = True
                if sub.finalbody:
                    flags["has_finally"] = True
            elif isinstance(sub, ast.Await):
                flags["awaits"] += 1
        cf_ref = f"cf://{owner}"
        graph.add_fact(BehaviorFact(ref=cf_ref, kind="control_flow", owner_ref=owner,
                                    label="control_flow", derivation="ast_control_flow",
                                    confidence=0.9, file=relposix, properties=flags))
        graph.add_relation(BehaviorRelation(owner, cf_ref, "has_control_flow",
                                            derivation="ast_control_flow", confidence=0.9, file=relposix))

        # routes (decorators)
        for dec in fn.decorator_list:
            route = self._route_from_decorator(dec)
            if route:
                rref = f"route://{route}"
                graph.add_fact(BehaviorFact(ref=rref, kind="route", label=route, owner_ref=owner,
                                            derivation="heuristic_static", confidence=0.7, file=relposix))
                graph.add_relation(BehaviorRelation(rref, owner, "handled_by",
                                                    derivation="heuristic_static", confidence=0.7, file=relposix))

        # side effects + state mutation + recovery
        self._py_side_effects(graph, owner, relposix, fn)
        self._py_state_and_recovery(graph, owner, relposix, fn, flags)

    def _py_side_effects(self, graph, owner, relposix, fn) -> None:
        for sub in ast.walk(fn):
            if not isinstance(sub, ast.Call):
                continue
            kind, resource, conf = self._classify_call(sub)
            if kind is None:
                continue
            se_ref = f"sideeffect://{owner}:{kind}:{resource or '?'}"
            graph.add_fact(BehaviorFact(ref=se_ref, kind="side_effect", owner_ref=owner,
                                        label=kind, derivation="heuristic_static", confidence=conf,
                                        file=relposix, properties={"resource": resource, "category": kind}))
            graph.add_relation(BehaviorRelation(owner, se_ref, "performs_side_effect",
                                                derivation="heuristic_static", confidence=conf, file=relposix))
            if kind == "database" and resource:
                graph.add_relation(BehaviorRelation(owner, f"table://{resource}", "persists_to",
                                                    derivation="heuristic_static", confidence=conf, file=relposix))

    def _py_state_and_recovery(self, graph, owner, relposix, fn, flags) -> None:
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Assign):
                for t in sub.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                        sref = f"state://{owner}:{t.attr}"
                        graph.add_fact(BehaviorFact(ref=sref, kind="state", label=t.attr, owner_ref=owner,
                                                    derivation="heuristic_static", confidence=0.6, file=relposix))
                        graph.add_relation(BehaviorRelation(owner, sref, "mutates_state",
                                                            derivation="heuristic_static", confidence=0.6, file=relposix))
        # recovery: a try whose except/finally calls a rollback-like function
        if flags["has_try"]:
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Try):
                    for h in sub.handlers:
                        for c in ast.walk(h):
                            name = self._call_name(c)
                            if name and name.lower() in _ROLLBACK_NAMES:
                                rref = f"recovery://{owner}:{name}"
                                graph.add_fact(BehaviorFact(ref=rref, kind="recovery", label=name, owner_ref=owner,
                                                            derivation="heuristic_static", confidence=0.6, file=relposix))
                                graph.add_relation(BehaviorRelation(owner, rref, "has_recovery",
                                                                    derivation="heuristic_static", confidence=0.6, file=relposix))
        # retry: a loop containing a try, or a decorator/name 'retry'
        has_retry = False
        for sub in ast.walk(fn):
            if isinstance(sub, (ast.For, ast.While)) and any(isinstance(x, ast.Try) for x in ast.walk(sub)):
                has_retry = True
        for dec in fn.decorator_list:
            if (self._call_name(dec) or "").lower().find("retry") >= 0:
                has_retry = True
        if has_retry:
            rref = f"recovery://{owner}:retry"
            graph.add_fact(BehaviorFact(ref=rref, kind="recovery", label="retry", owner_ref=owner,
                                        derivation="heuristic_static", confidence=0.6, file=relposix,
                                        properties={"pattern": "retry"}))
            graph.add_relation(BehaviorRelation(owner, rref, "has_recovery",
                                                derivation="heuristic_static", confidence=0.6, file=relposix))

    # -- JS UI path -----------------------------------------------------------

    _JS_EVENT = re.compile(r"""addEventListener\(\s*['"](\w+)['"]""")
    _JS_ONX = re.compile(r"""on(\w+)\s*[=:]""")
    _JS_FETCH = re.compile(r"""fetch\(\s*[`'"]([^`'"]+)['"`]""")
    _JS_AXIOS = re.compile(r"""axios\.(get|post|put|delete|patch)\(\s*[`'"]([^`'"]+)['"`]""")

    def _analyze_js(self, graph: BehavioralGraph, relpath: str, content: str, diags: list[str]) -> None:
        relposix = Path(relpath).as_posix()
        events = [m.group(1) for m in self._JS_EVENT.finditer(content)]
        events += [m.group(1).lower() for m in self._JS_ONX.finditer(content)]
        apis: list[tuple[str, str]] = [("get", m.group(1)) for m in self._JS_FETCH.finditer(content)]
        apis += [(m.group(1), m.group(2)) for m in self._JS_AXIOS.finditer(content)]

        ev_refs = []
        for i, ev in enumerate(sorted(set(events))):
            ref = f"uievent://{relposix}#{ev}:{i}"
            graph.add_fact(BehaviorFact(ref=ref, kind="ui_event", label=ev, owner_ref=f"file://{relposix}",
                                        derivation="heuristic_static", confidence=0.5, file=relposix))
            ev_refs.append(ref)
        for method, url in apis:
            api_ref = f"apicall://{relposix}#{method}:{url}"
            route = f"{method.upper()} {url}"
            graph.add_fact(BehaviorFact(ref=api_ref, kind="api_call", label=route, owner_ref=f"file://{relposix}",
                                        derivation="heuristic_static", confidence=0.5, file=relposix,
                                        properties={"route": route, "url": url}))
            # within-file linkage: each UI event may invoke each API call (heuristic).
            for ev in ev_refs:
                graph.add_relation(BehaviorRelation(ev, api_ref, "invokes",
                                                    derivation="heuristic_static", confidence=0.4, file=relposix))
            graph.add_relation(BehaviorRelation(api_ref, f"route://{route}", "reaches",
                                                derivation="heuristic_static", confidence=0.4, file=relposix))
        if not events and not apis:
            diags.append(f"behavioral: no UI events/api calls detected in {relposix}")

    # -- helpers --------------------------------------------------------------

    def _classify_call(self, call: ast.Call) -> tuple[str | None, str | None, float]:
        func = call.func
        name = self._call_name(call)
        recv = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
        # file
        if name == "open" or (isinstance(func, ast.Attribute) and func.attr in ("write_text", "read_text", "open")):
            return "file", self._first_str_arg(call), 0.6
        if recv in ("os", "shutil") or name in ("remove", "rmtree", "mkdir"):
            if recv in ("os", "shutil"):
                return "file", None, 0.5
        # database
        if isinstance(func, ast.Attribute) and func.attr in _DB_METHODS:
            sql = self._first_str_arg(call) or ""
            m = _SQL_TABLE.search(sql)
            return "database", (m.group(1) if m else None), 0.6
        # network
        if recv in _NET_MODULES or (isinstance(func, ast.Attribute) and func.attr in _HTTP_METHODS and recv in _NET_MODULES):
            return "network", self._first_str_arg(call), 0.6
        # process
        if recv == "subprocess" or name in ("system", "popen") or (isinstance(func, ast.Attribute) and func.attr in ("run", "Popen") and recv == "subprocess"):
            return "process", None, 0.6
        return None, None, 0.0

    @staticmethod
    def _route_from_decorator(dec: ast.AST) -> str | None:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            method = dec.func.attr.lower()
            if method in _HTTP_METHODS:
                path = None
                if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                    path = dec.args[0].value
                if path:
                    return f"{method.upper()} {path}"
        return None

    @staticmethod
    def _first_str_arg(call: ast.Call) -> str | None:
        for a in call.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                return a.value
        return None

    @staticmethod
    def _call_name(node: ast.AST) -> str | None:
        target = node.func if isinstance(node, ast.Call) else node
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
        return None

    @staticmethod
    def _qualname(tree: ast.Module, fn: ast.AST) -> str:
        # Find enclosing class for methods (single level; nested handled by walk parents).
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for b in node.body:
                    if b is fn:
                        return f"{node.name}.{fn.name}"
        return fn.name


# --- combined traces ---------------------------------------------------------


def trace_request_to_persistence(
    behavioral: BehavioralGraph,
    semantic: SemanticGraph,
    route_ref: str,
    *,
    max_depth: int = 8,
) -> dict:
    """From a route, follow the handler's resolved calls to reach DB side effects/tables."""
    handler = None
    for r in behavioral.out_relations(route_ref, kind="handled_by"):
        handler = r.target_ref
        break
    if handler is None:
        return {"route": route_ref, "handler": None, "path": [], "tables": [], "diagnostics": ["no handler"]}

    visited: set[str] = set()
    order: list[str] = []
    tables: list[str] = []
    frontier = [(handler, 0)]
    while frontier:
        ref, depth = frontier.pop(0)
        if ref in visited or depth > max_depth:
            continue
        visited.add(ref)
        order.append(ref)
        for rel in behavioral.out_relations(ref, kind="persists_to"):
            if rel.target_ref not in tables:
                tables.append(rel.target_ref)
        for e in semantic.out_edges(ref, kind="calls"):
            if e.resolved:
                frontier.append((e.target_ref, depth + 1))
    return {"route": route_ref, "handler": handler, "path": order, "tables": tables, "diagnostics": []}


def trace_ui_to_api(behavioral: BehavioralGraph, ui_event_ref: str) -> dict:
    """From a UI event, follow invokes -> api_call -> reaches route."""
    apis = [r.target_ref for r in behavioral.out_relations(ui_event_ref, kind="invokes")]
    routes: list[str] = []
    for api in apis:
        for r in behavioral.out_relations(api, kind="reaches"):
            routes.append(r.target_ref)
    return {"ui_event": ui_event_ref, "api_calls": apis, "routes": routes}
