"""LSP adapter with AST fallback (PI-6).

When a language server is available the analyzer can use richer resolution; when it is not
(the default in this environment), analysis falls back to the AST/heuristic analyzers and
records the degradation explicitly (it never silently claims LSP-quality results).

This adapter intentionally does not spawn a server in PI-6: ``available()`` returns False
unless an injected probe says otherwise, so behavior is deterministic and offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agent.project_twin.analyzers.registry import AnalysisResult, AnalyzerRegistry
from agent.project_twin.graph.semantic import SemanticGraph

LSP_FALLBACK_REASON = "lsp_unavailable_ast_fallback"


@dataclass
class LspAnalysis:
    result: AnalysisResult
    used_lsp: bool
    degraded: bool
    degradation_reasons: list[str]


class LspAdapter:
    def __init__(self, registry: AnalyzerRegistry, *, probe: Callable[[], bool] | None = None) -> None:
        self._registry = registry
        self._probe = probe or (lambda: False)

    def available(self) -> bool:
        try:
            return bool(self._probe())
        except Exception:
            return False

    def analyze(self, root: Path, files: dict[str, str], *, graph: SemanticGraph | None = None) -> LspAnalysis:
        result = self._registry.analyze_project(root, files, graph=graph)
        if self.available():
            return LspAnalysis(result=result, used_lsp=True, degraded=bool(result.degradations),
                               degradation_reasons=list(result.degradations))
        reasons = [LSP_FALLBACK_REASON, *result.degradations]
        return LspAnalysis(result=result, used_lsp=False, degraded=True, degradation_reasons=reasons)
