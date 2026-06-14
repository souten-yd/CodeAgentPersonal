"""Behavioral graph inference (PDT-8/PIR-7).

Infers expected/inferred project behavior into the `behavioral` domain:
- side-effect nodes (file/database/network/process/ui) for Python functions;
- a UI interaction path (event -> action -> api_call) from JS handlers and fetch calls;
- per-callable CFG, SSA-lite def/use, state/recovery, and resource identity facts;
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
from typing import Iterable

from agent.project_twin.contracts import (
    StaticAnalysisRequest,
    StaticAnalysisResult,
    TwinDelta,
    TwinEdge,
    TwinNode,
)
from agent.project_twin.static_graph import _iter_files, _rel, nid

ANALYZER_VERSION = "behavioral_graph.v3"
_DOMAIN = "behavioral"

_FILE_NAMES = {"open", "read", "write", "read_text", "write_text", "read_bytes",
               "write_bytes", "mkdir", "remove", "unlink", "rename", "listdir", "rglob", "glob"}
_DB_NAMES = {"execute", "executemany", "cursor", "commit", "connect", "fetchone", "fetchall"}
_NET_ROOTS = {"requests", "httpx", "urllib", "aiohttp", "socket"}
_NET_NAMES = {"urlopen", "request"}
_PROC_ROOTS = {"subprocess", "os"}
_PROC_NAMES = {"Popen", "system", "run", "call", "check_output", "check_call", "spawn"}
_UI_NAMES = {"render", "render_template", "template", "templates", "print"}
_STATE_FIELDS = {"state", "status", "phase", "stage", "mode"}
_ROLLBACK_NAMES = {"rollback", "abort", "revert", "undo", "compensate"}
_RETRY_NAMES = {"retry", "backoff", "sleep", "timeout"}
_EVENT_NAMES = {"emit", "publish", "dispatch", "send", "notify"}
_DB_TABLE = re.compile(r"\b(?:from|into|update|join)\s+([A-Za-z_][\w]*)", re.I)

_JS_FETCH = re.compile(r"""\bfetch\s*\(\s*["'`]([^"'`]+)["'`]""")
_JS_API = re.compile(r"""\b(?:api|client)\.(get|post|put|delete|patch)\s*\(\s*["'`]([^"'`]+)["'`]""")
_JS_LISTENER = re.compile(r"""addEventListener\s*\(\s*["']([a-zA-Z]+)["']""")
_JS_LISTENER_CALL = re.compile(r"""addEventListener\s*\(\s*["']([a-zA-Z]+)["']\s*,""")


class _Builder:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.now = datetime.now(timezone.utc)
        self.nodes: list[TwinNode] = []
        self.edges: list[TwinEdge] = []
        self.diagnostics: list[dict] = []
        self._sn: set[str] = set()
        self._se: set[str] = set()

    def node(self, *, node_type, canonical_ref, label, source_ref, kind=None, confidence=0.6, properties=None):
        if canonical_ref in self._sn:
            return nid(canonical_ref)
        self._sn.add(canonical_ref)
        props = dict(properties or {})
        if kind:
            props.setdefault("kind", kind)
        self.nodes.append(TwinNode(
            node_id=nid(canonical_ref), project_id=self.project_id, domain=_DOMAIN,
            node_type=node_type, canonical_ref=canonical_ref, label=label,
            properties=props, source_kind="git", source_ref=source_ref,
            derivation="heuristic_static", confidence=confidence, status="inferred",
            valid_from=self.now, created_at=self.now, updated_at=self.now,
        ))
        return nid(canonical_ref)

    def edge(self, *, edge_type, source_ref_node, target_ref_node, source_ref, confidence=0.6, properties=None):
        eid = nid(f"{edge_type}|{source_ref_node}|{target_ref_node}")
        if eid in self._se:
            return
        self._se.add(eid)
        self.edges.append(TwinEdge(
            edge_id=eid, project_id=self.project_id, domain=_DOMAIN,
            source_node_id=nid(source_ref_node), target_node_id=nid(target_ref_node),
            edge_type=edge_type, properties=dict(properties or {}), source_kind="git", source_ref=source_ref,
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


def _source_range(node: ast.AST) -> dict[str, int]:
    return {
        "start_line": int(getattr(node, "lineno", 0) or 0),
        "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0),
        "start_col": int(getattr(node, "col_offset", 0) or 0),
        "end_col": int(getattr(node, "end_col_offset", getattr(node, "col_offset", 0)) or 0),
    }


def _names_loaded(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _names_stored(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
            names.add(item.id)
        elif isinstance(item, ast.Attribute) and isinstance(item.ctx, ast.Store):
            parts = []
            cur: ast.AST = item
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                names.add(".".join(reversed(parts)))
    return names


def _literal_state(value: ast.AST) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, (str, int, bool)):
        return str(value.value)
    if isinstance(value, ast.Attribute):
        return value.attr
    if isinstance(value, ast.Name):
        return value.id
    return None


def _first_str_arg(call: ast.Call) -> str | None:
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _config_identity(call: ast.Call) -> str | None:
    """Env/config read identity for ``os.getenv(...)`` / ``os.environ.get(...)``, else None.

    A configuration/environment read is a behaviorally significant input (changing it can alter
    behavior), so model it as a `config` resource. Kept Call-based and conservative to avoid flagging
    every ``dict.get`` — only ``environ.get`` and ``getenv`` qualify.
    """
    root, name = _call_root_attr(call)
    if name == "getenv":  # os.getenv('X') or a bare getenv('X')
        return _first_str_arg(call) or "env"
    if name == "get" and isinstance(call.func, ast.Attribute):
        val = call.func.value
        if isinstance(val, ast.Attribute) and val.attr == "environ":
            return _first_str_arg(call) or "env"
        if isinstance(val, ast.Name) and val.id == "environ":
            return _first_str_arg(call) or "env"
    return None


_FILE_READ = {"read", "read_text", "read_bytes", "listdir", "rglob", "glob"}
_FILE_WRITE = {"write", "write_text", "write_bytes", "mkdir"}
_FILE_DELETE = {"remove", "unlink"}
_FILE_MUTATE = {"rename"}


def _open_mode(call: ast.Call) -> str:
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
        return call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return ""


def _resource_direction(kind: str, call: ast.Call) -> str:
    """Coarse read/write/mutate/delete/... direction of a resource effect (heuristic)."""
    _root, name = _call_root_attr(call)
    n = name or ""
    if kind == "file":
        if n in _FILE_DELETE:
            return "delete"
        if n in _FILE_MUTATE:
            return "mutate"
        if n in _FILE_WRITE:
            return "write"
        if n in _FILE_READ:
            return "read"
        if n == "open":
            return "write" if any(c in _open_mode(call) for c in ("w", "a", "x", "+")) else "read"
        return "read"
    if kind == "config":
        return "read"
    if kind == "database":
        if n in {"fetchone", "fetchall"}:
            return "read"
        if n in {"commit", "execute", "executemany"}:
            return "write"
        return "mutate"
    if kind == "network":
        return "call"
    if kind == "process":
        return "execute"
    if kind == "ui":
        return "render"
    return "use"


def _classify_resource(call: ast.Call) -> tuple[str | None, str | None]:
    root, name = _call_root_attr(call)
    first = _first_str_arg(call)
    if name in _FILE_NAMES:
        return "file", first
    if name in _DB_NAMES:
        table = _DB_TABLE.search(first or "")
        return "database", table.group(1) if table else None
    if root in _NET_ROOTS or name in _NET_NAMES:
        return "network", first
    if (root in _PROC_ROOTS and name in _PROC_NAMES) or name in {"Popen", "system"}:
        return "process", first
    if name in _UI_NAMES:
        return "ui", name
    cfg = _config_identity(call)
    if cfg is not None:
        return "config", cfg
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


def _cfg_ref(sym_ref: str, node: ast.AST | str, kind: str) -> str:
    if isinstance(node, str):
        return f"cfg://{sym_ref}/{node}"
    line = int(getattr(node, "lineno", 0) or 0)
    col = int(getattr(node, "col_offset", 0) or 0)
    return f"cfg://{sym_ref}/L{line}:{col}:{kind}"


def _call_name(call: ast.Call) -> str | None:
    root, name = _call_root_attr(call)
    return f"{root}.{name}" if root and name else name


def _local_call_target(call: ast.Call, local_functions: dict[str, str]) -> str | None:
    if isinstance(call.func, ast.Name):
        return local_functions.get(call.func.id)
    return None


def _emit_cfg(b: _Builder, rel: str, sym_ref: str, fn: ast.AST) -> None:
    entry = _cfg_ref(sym_ref, "entry", "entry")
    exit_ref = _cfg_ref(sym_ref, "exit", "exit")
    b.node(node_type="cfg_block", canonical_ref=entry, label=f"{sym_ref} entry", source_ref=rel,
           kind="entry", confidence=0.7, properties=_source_range(fn))
    b.node(node_type="cfg_block", canonical_ref=exit_ref, label=f"{sym_ref} exit", source_ref=rel,
           kind="exit", confidence=0.7, properties=_source_range(fn))
    b.edge(edge_type="cfg_entry", source_ref_node=sym_ref, target_ref_node=entry, source_ref=rel, confidence=0.7)

    prev = entry
    for stmt in getattr(fn, "body", []):
        kind = type(stmt).__name__.lower()
        current = _cfg_ref(sym_ref, stmt, kind)
        b.node(node_type="cfg_block", canonical_ref=current, label=f"{kind} L{getattr(stmt, 'lineno', 0)}",
               source_ref=rel, kind=kind, confidence=0.7, properties=_source_range(stmt))
        b.edge(edge_type="cfg_next", source_ref_node=prev, target_ref_node=current, source_ref=rel, confidence=0.7)

        if isinstance(stmt, ast.If):
            true_ref = _cfg_ref(sym_ref, stmt.body[0], "if_true") if stmt.body else exit_ref
            false_ref = _cfg_ref(sym_ref, stmt.orelse[0], "if_false") if stmt.orelse else exit_ref
            for ref, label in ((true_ref, "if true"), (false_ref, "if false")):
                b.node(node_type="cfg_block", canonical_ref=ref, label=label, source_ref=rel,
                       kind=label.replace(" ", "_"), confidence=0.7, properties=_source_range(stmt))
            b.edge(edge_type="cfg_condition_true", source_ref_node=current, target_ref_node=true_ref, source_ref=rel, confidence=0.7)
            b.edge(edge_type="cfg_condition_false", source_ref_node=current, target_ref_node=false_ref, source_ref=rel, confidence=0.7)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            body_ref = _cfg_ref(sym_ref, stmt.body[0], "loop_body") if stmt.body else current
            b.node(node_type="cfg_block", canonical_ref=body_ref, label="loop body", source_ref=rel,
                   kind="loop_body", confidence=0.7, properties=_source_range(stmt))
            b.edge(edge_type="cfg_condition_true", source_ref_node=current, target_ref_node=body_ref, source_ref=rel, confidence=0.7)
            b.edge(edge_type="cfg_loop_back", source_ref_node=body_ref, target_ref_node=current, source_ref=rel, confidence=0.7)
            b.edge(edge_type="cfg_condition_false", source_ref_node=current, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)
        elif isinstance(stmt, ast.Try):
            if stmt.handlers:
                handler = stmt.handlers[0]
                handler_ref = _cfg_ref(sym_ref, handler, "except")
                b.node(node_type="cfg_block", canonical_ref=handler_ref, label="except handler", source_ref=rel,
                       kind="except", confidence=0.7, properties=_source_range(handler))
                b.edge(edge_type="cfg_exception", source_ref_node=current, target_ref_node=handler_ref, source_ref=rel, confidence=0.7)
            if stmt.finalbody:
                finally_ref = _cfg_ref(sym_ref, stmt.finalbody[0], "finally")
                b.node(node_type="cfg_block", canonical_ref=finally_ref, label="finally", source_ref=rel,
                       kind="finally", confidence=0.7, properties=_source_range(stmt.finalbody[0]))
                b.edge(edge_type="cfg_finally", source_ref_node=current, target_ref_node=finally_ref, source_ref=rel, confidence=0.7)
        elif isinstance(stmt, ast.Return):
            b.edge(edge_type="cfg_return", source_ref_node=current, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)
        elif isinstance(stmt, ast.Raise):
            b.edge(edge_type="cfg_raise", source_ref_node=current, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)
        prev = current
    b.edge(edge_type="cfg_exit", source_ref_node=prev, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)
    for sub in ast.walk(fn):
        if sub is fn or not isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Return, ast.Raise)):
            continue
        kind = type(sub).__name__.lower()
        current = _cfg_ref(sym_ref, sub, kind)
        b.node(node_type="cfg_block", canonical_ref=current, label=f"{kind} L{getattr(sub, 'lineno', 0)}",
               source_ref=rel, kind=kind, confidence=0.7, properties=_source_range(sub))
        if isinstance(sub, ast.If):
            true_ref = _cfg_ref(sym_ref, sub.body[0], "if_true") if sub.body else exit_ref
            false_ref = _cfg_ref(sym_ref, sub.orelse[0], "if_false") if sub.orelse else exit_ref
            b.edge(edge_type="cfg_condition_true", source_ref_node=current, target_ref_node=true_ref, source_ref=rel, confidence=0.7)
            b.edge(edge_type="cfg_condition_false", source_ref_node=current, target_ref_node=false_ref, source_ref=rel, confidence=0.7)
        elif isinstance(sub, (ast.For, ast.AsyncFor, ast.While)):
            body_ref = _cfg_ref(sym_ref, sub.body[0], "loop_body") if sub.body else current
            b.edge(edge_type="cfg_condition_true", source_ref_node=current, target_ref_node=body_ref, source_ref=rel, confidence=0.7)
            b.edge(edge_type="cfg_loop_back", source_ref_node=body_ref, target_ref_node=current, source_ref=rel, confidence=0.7)
            b.edge(edge_type="cfg_condition_false", source_ref_node=current, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)
        elif isinstance(sub, ast.Try):
            if sub.handlers:
                handler = sub.handlers[0]
                handler_ref = _cfg_ref(sym_ref, handler, "except")
                b.node(node_type="cfg_block", canonical_ref=handler_ref, label="except handler", source_ref=rel,
                       kind="except", confidence=0.7, properties=_source_range(handler))
                b.edge(edge_type="cfg_exception", source_ref_node=current, target_ref_node=handler_ref, source_ref=rel, confidence=0.7)
            if sub.finalbody:
                finally_ref = _cfg_ref(sym_ref, sub.finalbody[0], "finally")
                b.node(node_type="cfg_block", canonical_ref=finally_ref, label="finally", source_ref=rel,
                       kind="finally", confidence=0.7, properties=_source_range(sub.finalbody[0]))
                b.edge(edge_type="cfg_finally", source_ref_node=current, target_ref_node=finally_ref, source_ref=rel, confidence=0.7)
        elif isinstance(sub, ast.Return):
            b.edge(edge_type="cfg_return", source_ref_node=current, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)
        elif isinstance(sub, ast.Raise):
            b.edge(edge_type="cfg_raise", source_ref_node=current, target_ref_node=exit_ref, source_ref=rel, confidence=0.7)


def _emit_behavior_facts(b: _Builder, rel: str, sym_ref: str, fn: ast.AST, local_functions: dict[str, str]) -> None:
    last_defs: dict[str, str] = {}
    state_seen: dict[str, str] = {}

    args = getattr(fn, "args", None)
    for arg in getattr(args, "args", []) + getattr(args, "posonlyargs", []) + getattr(args, "kwonlyargs", []):
        var_ref = f"var://{sym_ref}/{arg.arg}"
        b.node(node_type="variable", canonical_ref=var_ref, label=arg.arg, source_ref=rel,
               kind="parameter", confidence=0.7, properties=_source_range(arg))
        b.edge(edge_type="defines", source_ref_node=sym_ref, target_ref_node=var_ref, source_ref=rel, confidence=0.7)
        last_defs[arg.arg] = var_ref

    for sub in ast.walk(fn):
        if isinstance(sub, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = sub.value if not isinstance(sub, ast.AugAssign) else sub.value
            targets: Iterable[ast.AST]
            if isinstance(sub, ast.Assign):
                targets = sub.targets
            else:
                targets = [sub.target]
            used = _names_loaded(value) if value is not None else set()
            for target in targets:
                for name in _names_stored(target):
                    def_ref = f"def://{sym_ref}/L{getattr(sub, 'lineno', 0)}:{name}"
                    b.node(node_type="definition", canonical_ref=def_ref, label=name, source_ref=rel,
                           kind="assignment", confidence=0.7, properties=_source_range(sub))
                    b.edge(edge_type="defines", source_ref_node=sym_ref, target_ref_node=def_ref, source_ref=rel, confidence=0.7)
                    for used_name in used:
                        if used_name in last_defs:
                            b.edge(edge_type="flows_to", source_ref_node=last_defs[used_name], target_ref_node=def_ref,
                                   source_ref=rel, confidence=0.65)
                    last_defs[name] = def_ref

                    field = name.rsplit(".", 1)[-1]
                    state_value = _literal_state(value) if value is not None else None
                    if field in _STATE_FIELDS and state_value is not None:
                        state_ref = f"state://{sym_ref}/{field}/{state_value}"
                        b.node(node_type="state", canonical_ref=state_ref, label=f"{field}={state_value}", source_ref=rel,
                               kind=field, confidence=0.65, properties=_source_range(sub))
                        previous = state_seen.get(field)
                        if previous:
                            b.edge(edge_type="state_transition", source_ref_node=previous, target_ref_node=state_ref,
                                   source_ref=rel, confidence=0.6)
                        b.edge(edge_type="mutates_state", source_ref_node=sym_ref, target_ref_node=state_ref,
                               source_ref=rel, confidence=0.65)
                        state_seen[field] = state_ref

        if isinstance(sub, ast.Call):
            kind, identity = _classify_resource(sub)
            if kind:
                direction = _resource_direction(kind, sub)
                res_ref = f"resource://{kind}:{identity or 'unknown'}"
                # Direction is part of the effect identity so a function that both reads and writes the
                # same resource produces two distinct, non-colliding side-effect nodes.
                se_ref = f"side_effect://{sym_ref}/{kind}/{identity or 'unknown'}/{direction}"
                b.node(node_type="resource", canonical_ref=res_ref, label=identity or kind, source_ref=rel,
                       kind=kind, confidence=0.65, properties={**_source_range(sub), "identity": identity})
                b.node(node_type="side_effect", canonical_ref=se_ref, label=f"{kind} {direction} effect", source_ref=rel,
                       kind=kind, confidence=0.65, properties={**_source_range(sub), "resource": identity, "direction": direction})
                b.edge(edge_type="performs_side_effect", source_ref_node=sym_ref, target_ref_node=se_ref,
                       source_ref=rel, confidence=0.65, properties={"direction": direction})
                b.edge(edge_type="targets_resource", source_ref_node=se_ref, target_ref_node=res_ref,
                       source_ref=rel, confidence=0.65, properties={"direction": direction})
                if kind == "database" and identity:
                    b.edge(edge_type="persists_to", source_ref_node=sym_ref, target_ref_node=res_ref,
                           source_ref=rel, confidence=0.65)
                for name in _names_loaded(sub):
                    if name in last_defs:
                        b.edge(edge_type="flows_to_resource", source_ref_node=last_defs[name], target_ref_node=res_ref,
                               source_ref=rel, confidence=0.6)

            name = (_call_name(sub) or "").lower()
            if any(part in name for part in _ROLLBACK_NAMES):
                rec_ref = f"recovery://{sym_ref}/rollback/L{getattr(sub, 'lineno', 0)}"
                b.node(node_type="recovery", canonical_ref=rec_ref, label="rollback", source_ref=rel,
                       kind="rollback", confidence=0.65, properties=_source_range(sub))
                b.edge(edge_type="has_recovery", source_ref_node=sym_ref, target_ref_node=rec_ref, source_ref=rel, confidence=0.65)
            if any(part in name for part in _RETRY_NAMES):
                rec_ref = f"recovery://{sym_ref}/{name}/L{getattr(sub, 'lineno', 0)}"
                b.node(node_type="recovery", canonical_ref=rec_ref, label=name, source_ref=rel,
                       kind="retry", confidence=0.6, properties=_source_range(sub))
                b.edge(edge_type="has_recovery", source_ref_node=sym_ref, target_ref_node=rec_ref, source_ref=rel, confidence=0.6)
            if any(part == name or name.endswith(f".{part}") for part in _EVENT_NAMES):
                ev_name = _first_str_arg(sub) or name
                event_ref = f"event://{ev_name}"
                b.node(node_type="event", canonical_ref=event_ref, label=ev_name, source_ref=rel,
                       kind="producer", confidence=0.55, properties=_source_range(sub))
                b.edge(edge_type="produces_event", source_ref_node=sym_ref, target_ref_node=event_ref,
                       source_ref=rel, confidence=0.55)

            target = _local_call_target(sub, local_functions)
            if target is not None:
                for name in _names_loaded(sub):
                    if name in last_defs:
                        b.edge(edge_type="interprocedural_argument_flow", source_ref_node=last_defs[name], target_ref_node=target,
                               source_ref=rel, confidence=0.55)

        if isinstance(sub, ast.Return):
            ret_ref = f"return://{sym_ref}/L{getattr(sub, 'lineno', 0)}"
            b.node(node_type="return", canonical_ref=ret_ref, label="return", source_ref=rel,
                   kind="return", confidence=0.7, properties=_source_range(sub))
            for name in _names_loaded(sub.value) if sub.value is not None else set():
                if name in last_defs:
                    b.edge(edge_type="flows_to_return", source_ref_node=last_defs[name], target_ref_node=ret_ref,
                           source_ref=rel, confidence=0.65)

    for sub in ast.walk(fn):
        if isinstance(sub, (ast.For, ast.While, ast.AsyncFor)) and any(isinstance(item, ast.Try) for item in ast.walk(sub)):
            rec_ref = f"recovery://{sym_ref}/retry/L{getattr(sub, 'lineno', 0)}"
            b.node(node_type="recovery", canonical_ref=rec_ref, label="retry", source_ref=rel,
                   kind="retry", confidence=0.65, properties=_source_range(sub))
            b.edge(edge_type="has_recovery", source_ref_node=sym_ref, target_ref_node=rec_ref, source_ref=rel, confidence=0.65)


def _analyze_python(b: _Builder, root: Path, path: Path) -> None:
    rel = _rel(root, path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError) as exc:
        b.diagnostics.append({"code": "behavior_parse_skip", "file": rel, "detail": str(exc)})
        return

    local_functions: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local_functions[node.name] = f"py://{rel}#{node.name}"
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    local_functions[item.name] = f"py://{rel}#{node.name}.{item.name}"

    def emit(fn, qual):
        sym_ref = f"py://{rel}#{qual}"
        _emit_cfg(b, rel, sym_ref, fn)
        _emit_behavior_facts(b, rel, sym_ref, fn, local_functions)
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

    handlers = _js_handlers(text)
    events = sorted({event for event, _ in handlers} or set(_JS_LISTENER.findall(text)))
    file_targets = _js_api_targets(text)

    for evt in events:
        ev_ref = f"uievent://{rel}#{evt}"
        ac_ref = f"uiaction://{rel}#{evt}"
        b.node(node_type="event", canonical_ref=ev_ref, label=f"UI {evt}", source_ref=rel, kind="ui", confidence=0.5)
        b.node(node_type="action", canonical_ref=ac_ref, label=f"handle {evt}", source_ref=rel, kind="ui", confidence=0.5)
        b.edge(edge_type="triggers", source_ref_node=ev_ref, target_ref_node=ac_ref, source_ref=rel, confidence=0.5)
        handler_bodies = [body for event, body in handlers if event == evt]
        targets = []
        for body in handler_bodies:
            targets.extend(_js_api_targets(body))
        if targets:
            for method, url in targets:
                call_ref = f"apicall://{rel}#{method}:{url}"
                legacy_call_ref = f"apicall://{rel}#{url}"
                resource_ref = f"resource://api:{method.upper()} {url}"
                b.node(node_type="resource", canonical_ref=resource_ref, label=f"{method.upper()} {url}",
                       source_ref=rel, kind="api", confidence=0.5, properties={"identity": f"{method.upper()} {url}"})
                b.node(node_type="api_call", canonical_ref=call_ref, label=f"call {method.upper()} {url}",
                       source_ref=rel, kind="network", confidence=0.5, properties={"method": method.upper(), "url": url})
                b.node(node_type="api_call", canonical_ref=legacy_call_ref, label=f"call {url}",
                       source_ref=rel, kind="network", confidence=0.5, properties={"method": method.upper(), "url": url})
                b.edge(edge_type="invokes", source_ref_node=ac_ref, target_ref_node=call_ref, source_ref=rel, confidence=0.5)
                b.edge(edge_type="invokes", source_ref_node=ac_ref, target_ref_node=legacy_call_ref, source_ref=rel, confidence=0.5)
                b.edge(edge_type="targets_resource", source_ref_node=call_ref, target_ref_node=resource_ref, source_ref=rel, confidence=0.5)
                b.edge(edge_type="reaches_route", source_ref_node=call_ref,
                       target_ref_node=f"route://{method.upper()} {url}", source_ref=rel, confidence=0.45)
                b.edge(edge_type="reaches_route", source_ref_node=legacy_call_ref,
                       target_ref_node=f"route://{method.upper()} {url}", source_ref=rel, confidence=0.4)
        else:
            b.diagnostics.append({"code": "ui_action_target_unresolved", "file": rel, "event": evt})
    for method, url in file_targets:
        b.node(node_type="api_call", canonical_ref=f"apicall://{rel}#{method}:{url}",
               label=f"call {method.upper()} {url}", source_ref=rel, kind="network",
               confidence=0.5, properties={"method": method.upper(), "url": url})


def _js_api_targets(text: str) -> list[tuple[str, str]]:
    return [("get", u) for u in _JS_FETCH.findall(text)] + [(method, url) for method, url in _JS_API.findall(text)]


def _js_handlers(text: str) -> list[tuple[str, str]]:
    handlers: list[tuple[str, str]] = []
    for match in _JS_LISTENER_CALL.finditer(text):
        event = match.group(1)
        body_start = text.find("{", match.end())
        if body_start < 0:
            continue
        body_end = _matching_brace(text, body_start)
        if body_end < 0:
            continue
        handlers.append((event, text[body_start + 1:body_end]))
    return handlers


def _matching_brace(text: str, start: int) -> int:
    depth = 0
    quote: str | None = None
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


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
