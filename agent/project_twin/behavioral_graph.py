"""Behavioral graph inference (PDT-8).

Infers expected/inferred project behavior into the `behavioral` domain:
- side-effect nodes (file/database/network/process/ui) for Python functions;
- a UI interaction path (event -> action -> api_call) from JS handlers and fetch calls;
- data-flow / side-effect relations and explicit confidence.

Every behavioral fact is heuristic: derivation is `heuristic_static`, status is `inferred`,
and confidence is below 1.0. Behavioral facts are NEVER marked verified — only runtime
observation/verification can do that (PDT-9/PDT-10). Unresolved behavior emits uncertainty
diagnostics instead of fabricated certainty.
"""

from __future__ import annotations

import ast
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
from agent.project_twin.static_graph import _iter_files, _rel, nid

ANALYZER_VERSION = "behavioral_graph.v1"
_DOMAIN = "behavioral"

_FILE_NAMES = {"open", "read", "write", "read_text", "write_text", "read_bytes",
               "write_bytes", "mkdir", "remove", "unlink", "rename", "listdir", "rglob", "glob"}
_DB_NAMES = {"execute", "executemany", "cursor", "commit", "connect", "fetchone", "fetchall"}
_NET_ROOTS = {"requests", "httpx", "urllib", "aiohttp", "socket"}
_NET_NAMES = {"urlopen", "request"}
_PROC_ROOTS = {"subprocess", "os"}
_PROC_NAMES = {"Popen", "system", "run", "call", "check_output", "check_call", "spawn"}
_UI_NAMES = {"render", "render_template", "template", "templates", "print"}

_JS_FETCH = re.compile(r"""\bfetch\s*\(\s*["'`]([^"'`]+)["'`]""")
_JS_API = re.compile(r"""\b(?:api|client)\.(get|post|put|delete|patch)\s*\(\s*["'`]([^"'`]+)["'`]""")
_JS_LISTENER = re.compile(r"""addEventListener\s*\(\s*["']([a-zA-Z]+)["']""")


class _Builder:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.now = datetime.now(timezone.utc)
        self.nodes: list[TwinNode] = []
        self.edges: list[TwinEdge] = []
        self.diagnostics: list[dict] = []
        self._sn: set[str] = set()
        self._se: set[str] = set()

    def node(self, *, node_type, canonical_ref, label, source_ref, kind=None, confidence=0.6):
        if canonical_ref in self._sn:
            return nid(canonical_ref)
        self._sn.add(canonical_ref)
        self.nodes.append(TwinNode(
            node_id=nid(canonical_ref), project_id=self.project_id, domain=_DOMAIN,
            node_type=node_type, canonical_ref=canonical_ref, label=label,
            properties={"kind": kind} if kind else {}, source_kind="git", source_ref=source_ref,
            derivation="heuristic_static", confidence=confidence, status="inferred",
            valid_from=self.now, created_at=self.now, updated_at=self.now,
        ))
        return nid(canonical_ref)

    def edge(self, *, edge_type, source_ref_node, target_ref_node, source_ref, confidence=0.6):
        eid = nid(f"{edge_type}|{source_ref_node}|{target_ref_node}")
        if eid in self._se:
            return
        self._se.add(eid)
        self.edges.append(TwinEdge(
            edge_id=eid, project_id=self.project_id, domain=_DOMAIN,
            source_node_id=nid(source_ref_node), target_node_id=nid(target_ref_node),
            edge_type=edge_type, source_kind="git", source_ref=source_ref,
            derivation="heuristic_static", confidence=confidence, status="inferred",
            valid_from=self.now, created_at=self.now, updated_at=self.now,
        ))


def _call_root_attr(call: ast.Call) -> tuple[str | None, str | None]:
    func = call.func
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        root = func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        root_name = root.id if isinstance(root, ast.Name) else None
        return root_name, func.attr
    return None, None


def _classify_side_effects(fn: ast.AST) -> set[str]:
    kinds: set[str] = set()
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Call):
            continue
        root, name = _call_root_attr(sub)
        if name in _FILE_NAMES:
            kinds.add("file")
        if name in _DB_NAMES:
            kinds.add("database")
        if (root in _NET_ROOTS) or (name in _NET_NAMES):
            kinds.add("network")
        if (root in _PROC_ROOTS and name in _PROC_NAMES) or name in {"Popen", "system"}:
            kinds.add("process")
        if name in _UI_NAMES:
            kinds.add("ui")
    return kinds


def _analyze_python(b: _Builder, root: Path, path: Path) -> None:
    rel = _rel(root, path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError) as exc:
        b.diagnostics.append({"code": "behavior_parse_skip", "file": rel, "detail": str(exc)})
        return

    def emit(fn, qual):
        sym_ref = f"py://{rel}#{qual}"
        for kind in sorted(_classify_side_effects(fn)):
            se_ref = f"side_effect://{rel}#{qual}/{kind}"
            b.node(node_type="side_effect", canonical_ref=se_ref, label=f"{qual} {kind} effect", source_ref=rel, kind=kind)
            b.edge(edge_type="performs_side_effect", source_ref_node=sym_ref, target_ref_node=se_ref, source_ref=rel)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            emit(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    emit(item, f"{node.name}.{item.name}")


def _analyze_js(b: _Builder, root: Path, path: Path) -> None:
    rel = _rel(root, path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        b.diagnostics.append({"code": "behavior_read_skip", "file": rel, "detail": str(exc)})
        return

    events = sorted(set(_JS_LISTENER.findall(text)))
    targets = [u for u in _JS_FETCH.findall(text)] + [u for _, u in _JS_API.findall(text)]
    for evt in events:
        ev_ref = f"uievent://{rel}#{evt}"
        ac_ref = f"uiaction://{rel}#{evt}"
        b.node(node_type="event", canonical_ref=ev_ref, label=f"UI {evt}", source_ref=rel, kind="ui", confidence=0.5)
        b.node(node_type="action", canonical_ref=ac_ref, label=f"handle {evt}", source_ref=rel, kind="ui", confidence=0.5)
        b.edge(edge_type="triggers", source_ref_node=ev_ref, target_ref_node=ac_ref, source_ref=rel, confidence=0.5)
        if targets:
            for url in targets:
                call_ref = f"apicall://{rel}#{url}"
                b.node(node_type="api_call", canonical_ref=call_ref, label=f"call {url}", source_ref=rel, kind="network", confidence=0.5)
                b.edge(edge_type="invokes", source_ref_node=ac_ref, target_ref_node=call_ref, source_ref=rel, confidence=0.5)
                # link to the structural FastAPI route if the path matches (inferred)
                for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    b.edge(edge_type="reaches_route", source_ref_node=call_ref,
                           target_ref_node=f"route://{method} {url}", source_ref=rel, confidence=0.4)
        else:
            b.diagnostics.append({"code": "ui_action_target_unresolved", "file": rel, "event": evt})


class BehavioralAnalyzer:
    def analyze(self, request: StaticAnalysisRequest) -> StaticAnalysisResult:
        root = Path(request.project_path)
        b = _Builder(request.project_id)
        if not root.is_dir():
            b.diagnostics.append({"code": "project_path_missing", "detail": request.project_path})
        else:
            changed = None if request.full_rebuild else (request.changed_paths or None)
            for path in _iter_files(root, changed):
                if path.suffix == ".py":
                    _analyze_python(b, root, path)
                elif path.suffix == ".js":
                    _analyze_js(b, root, path)

        delta = TwinDelta(
            project_id=request.project_id, base_revision_id=request.base_revision_id,
            idempotency_key=f"behavior:{ANALYZER_VERSION}:{','.join(sorted(request.changed_paths)) or 'full'}:{b.now.isoformat()}",
            trigger_type="behavioral_analysis", trigger_ref=ANALYZER_VERSION,
            nodes=b.nodes, edges=b.edges, diagnostics=b.diagnostics,
        )
        return StaticAnalysisResult(project_id=request.project_id, delta=delta,
                                    parser_versions={"behavioral_graph": ANALYZER_VERSION},
                                    diagnostics=b.diagnostics)
