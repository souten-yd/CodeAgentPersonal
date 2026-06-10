"""Semantic graph model for the Digital Twin (PI-6).

A deterministic, language-agnostic node/edge model with stable canonical refs. It backs the
real semantic foundation (resolved/candidate calls, inheritance, aliases, re-exports) that
replaces Core v1's name-based extraction. It is pure data: no SQLite, no framework.

Canonical ref scheme (deterministic and collision-free across modules):

```text
file://<relpath>
pkg://<dotted.package>
module://<dotted.module>
py://<dotted.module>#<qualname>     (Python symbols)
js://<relpath>#<name>               (JS/TS symbols)
vue://<relpath>#<component>         (Vue components)
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# Node kinds.
NODE_KINDS = {
    "repository", "directory", "file", "package", "module",
    "class", "function", "method", "variable", "type", "import",
    "component",
}

# Edge kinds.
EDGE_KINDS = {
    "contains", "defines", "imports", "references", "aliases", "reexports",
    "inherits", "overrides", "implements", "decorates", "depends_on", "calls",
}


@dataclass(frozen=True)
class SemanticNode:
    ref: str
    kind: str
    name: str
    module: str = ""
    qualname: str = ""
    file: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticEdge:
    source_ref: str
    target_ref: str
    kind: str
    resolved: bool = True
    confidence: float = 1.0
    file: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


class SemanticGraph:
    """An incrementally-updatable semantic graph keyed by canonical ref."""

    def __init__(self) -> None:
        self._nodes: dict[str, SemanticNode] = {}
        # edge identity = (source, target, kind) so re-analysis is idempotent.
        self._edges: dict[tuple[str, str, str], SemanticEdge] = {}

    # -- mutation -------------------------------------------------------------

    def add_node(self, node: SemanticNode) -> None:
        if node.kind not in NODE_KINDS:
            raise ValueError(f"unknown node kind {node.kind!r}")
        # First writer wins for identity; merge properties additively.
        existing = self._nodes.get(node.ref)
        if existing is None:
            self._nodes[node.ref] = node
        elif node.properties:
            merged = {**existing.properties, **node.properties}
            self._nodes[node.ref] = SemanticNode(
                ref=existing.ref, kind=existing.kind, name=existing.name,
                module=existing.module, qualname=existing.qualname,
                file=existing.file or node.file, properties=merged,
            )

    def add_edge(self, edge: SemanticEdge) -> None:
        if edge.kind not in EDGE_KINDS:
            raise ValueError(f"unknown edge kind {edge.kind!r}")
        key = (edge.source_ref, edge.target_ref, edge.kind)
        prior = self._edges.get(key)
        # A resolved edge supersedes a candidate one for the same triple.
        if prior is None or (edge.resolved and not prior.resolved):
            self._edges[key] = edge

    def merge(self, nodes: Iterable[SemanticNode], edges: Iterable[SemanticEdge]) -> None:
        for n in nodes:
            self.add_node(n)
        for e in edges:
            self.add_edge(e)

    def invalidate_file(self, relpath: str) -> tuple[int, int]:
        """Remove all nodes/edges sourced from a file (incremental invalidation)."""
        n_before, e_before = len(self._nodes), len(self._edges)
        self._nodes = {r: n for r, n in self._nodes.items() if n.file != relpath}
        self._edges = {k: e for k, e in self._edges.items() if e.file != relpath}
        return n_before - len(self._nodes), e_before - len(self._edges)

    # -- queries --------------------------------------------------------------

    def get(self, ref: str) -> SemanticNode | None:
        return self._nodes.get(ref)

    def nodes(self, *, kind: str | None = None) -> list[SemanticNode]:
        items = sorted(self._nodes.values(), key=lambda n: n.ref)
        return [n for n in items if kind is None or n.kind == kind]

    def edges(self, *, kind: str | None = None, resolved: bool | None = None) -> list[SemanticEdge]:
        items = sorted(self._edges.values(), key=lambda e: (e.source_ref, e.target_ref, e.kind))
        out = []
        for e in items:
            if kind is not None and e.kind != kind:
                continue
            if resolved is not None and e.resolved != resolved:
                continue
            out.append(e)
        return out

    def out_edges(self, ref: str, *, kind: str | None = None) -> list[SemanticEdge]:
        return [e for e in self.edges(kind=kind) if e.source_ref == ref]

    def candidates(self) -> list[SemanticEdge]:
        """Unresolved (may-call / may-reference) edges with confidence < 1."""
        return self.edges(resolved=False)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)
