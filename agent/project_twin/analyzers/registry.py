"""Analyzer registry and coarse analysis result (PI-6).

The registry maps file suffixes to language analyzers, each of which exposes a single
``analyze(root, relpath, content)`` operation plus a capability/version manifest. The
project-level ``analyze_project`` builds one ``SemanticGraph`` across files and records
degradations and an old-CodeIntel parity metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from agent.project_twin.graph.semantic import SemanticEdge, SemanticGraph, SemanticNode


@dataclass(frozen=True)
class AnalyzerCapability:
    language: str
    version: str
    capabilities: frozenset[str]


@dataclass
class AnalyzerOutput:
    nodes: list[SemanticNode] = field(default_factory=list)
    edges: list[SemanticEdge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    degraded: bool = False


class LanguageAnalyzer(Protocol):
    suffixes: tuple[str, ...]

    def capability(self) -> AnalyzerCapability: ...
    def analyze(self, root: Path, relpath: str, content: str) -> AnalyzerOutput: ...


@dataclass
class AnalysisResult:
    graph: SemanticGraph
    manifests: list[AnalyzerCapability]
    degradations: list[str]
    parity: dict[str, object]
    analyzed_files: int


class AnalyzerRegistry:
    """Dispatches files to analyzers and assembles the semantic graph."""

    def __init__(self, analyzers: list[LanguageAnalyzer]) -> None:
        self._analyzers = list(analyzers)
        self._by_suffix: dict[str, LanguageAnalyzer] = {}
        for a in self._analyzers:
            for suf in a.suffixes:
                self._by_suffix[suf] = a

    def analyzer_for(self, relpath: str) -> LanguageAnalyzer | None:
        return self._by_suffix.get(Path(relpath).suffix.lower())

    def manifests(self) -> list[AnalyzerCapability]:
        return [a.capability() for a in self._analyzers]

    def analyze_project(
        self,
        root: Path,
        files: dict[str, str],
        *,
        graph: SemanticGraph | None = None,
    ) -> AnalysisResult:
        """Analyze ``{relpath: content}`` into a semantic graph (deterministic order)."""
        graph = graph or SemanticGraph()
        degradations: list[str] = []
        analyzed = 0
        for relpath in sorted(files):
            analyzer = self.analyzer_for(relpath)
            if analyzer is None:
                continue
            # Incremental: drop prior facts for this file before re-adding.
            graph.invalidate_file(relpath)
            out = analyzer.analyze(root, relpath, files[relpath])
            graph.merge(out.nodes, out.edges)
            if out.degraded:
                degradations.extend(out.diagnostics)
            analyzed += 1
        self._link_reexports(graph)
        return AnalysisResult(
            graph=graph,
            manifests=self.manifests(),
            degradations=degradations,
            parity={},
            analyzed_files=analyzed,
        )

    @staticmethod
    def _link_reexports(graph: SemanticGraph) -> None:
        """Resolve module re-export aliases after all files have been analyzed."""
        aliases: dict[str, str] = {}
        for edge in graph.edges(kind="reexports"):
            if not edge.target_ref.startswith("py://"):
                continue
            module_ref = edge.source_ref.removeprefix("module://")
            name = edge.target_ref.rsplit("#", 1)[-1]
            aliases[f"py://{module_ref}#{name}"] = edge.target_ref
        if not aliases:
            return
        additions: list[SemanticEdge] = []
        for edge in graph.edges():
            target = aliases.get(edge.target_ref)
            if target is None:
                continue
            additions.append(
                SemanticEdge(
                    source_ref=edge.source_ref,
                    target_ref=target,
                    kind=edge.kind,
                    resolved=edge.resolved,
                    confidence=edge.confidence,
                    file=edge.file,
                    properties={**edge.properties, "via_reexport": edge.target_ref},
                )
            )
        for edge in additions:
            graph.add_edge(edge)


def compute_codeintel_parity(graph: SemanticGraph, codeintel_symbol_names: set[str]) -> dict[str, object]:
    """Record parity vs old CodeIntel: how many CodeIntel symbol names the v2 graph covers.

    The graph is collision-free across modules, so names are compared as a set. Returns
    matched/missing counts and a coverage ratio (recorded, not gated, per migration plan).
    """
    graph_names = {
        n.name for n in graph.nodes() if n.kind in ("function", "method", "class", "variable")
    }
    matched = sorted(codeintel_symbol_names & graph_names)
    missing = sorted(codeintel_symbol_names - graph_names)
    total = len(codeintel_symbol_names)
    return {
        "codeintel_symbols": total,
        "matched": len(matched),
        "missing": missing,
        "coverage": (len(matched) / total) if total else 1.0,
    }
