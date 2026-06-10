"""Default analyzer registry composition (PI-6).

Kept separate from ``registry`` so the analyzer modules can import the registry types
without an import cycle.
"""

from __future__ import annotations

from agent.project_twin.analyzers.javascript import JavaScriptAnalyzer
from agent.project_twin.analyzers.python import PythonAnalyzer
from agent.project_twin.analyzers.registry import AnalyzerRegistry
from agent.project_twin.analyzers.typescript_vue import TypeScriptVueAnalyzer


def build_default_registry() -> AnalyzerRegistry:
    return AnalyzerRegistry([
        PythonAnalyzer(),
        JavaScriptAnalyzer(),
        TypeScriptVueAnalyzer(),
    ])
