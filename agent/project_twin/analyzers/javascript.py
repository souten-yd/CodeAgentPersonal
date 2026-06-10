"""JavaScript basic semantic analyzer (PI-6).

Regex-based (heuristic) extraction of modules, imports and top-level function/const
declarations. Heuristic facts carry confidence < 1.0 and are never marked resolved beyond
import targets. Real call resolution is future work; this provides the JS/TS/Vue baseline
the acceptance criteria require.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent.project_twin.analyzers.registry import AnalyzerCapability, AnalyzerOutput
from agent.project_twin.graph.semantic import SemanticEdge, SemanticNode

_VERSION = "js-sem-2.0"
_CAPS = frozenset({"modules", "imports", "symbols"})

_IMPORT_FROM = re.compile(r"""import\s+(?:[\w*\s{},]+?)\s+from\s+['"]([^'"]+)['"]""")
_IMPORT_BARE = re.compile(r"""import\s+['"]([^'"]+)['"]""")
_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_FUNC = re.compile(r"""^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)""", re.M)
_CONST_FN = re.compile(r"""^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(""", re.M)


def _file_ref(relpath: str) -> str:
    return f"file://{Path(relpath).as_posix()}"


def _module_ref(relpath: str) -> str:
    return f"module://{Path(relpath).as_posix()}"


def _sym_ref(relpath: str, name: str) -> str:
    return f"js://{Path(relpath).as_posix()}#{name}"


class JavaScriptAnalyzer:
    suffixes = (".js", ".jsx", ".mjs", ".cjs")

    def capability(self) -> AnalyzerCapability:
        return AnalyzerCapability(language="javascript", version=_VERSION, capabilities=_CAPS)

    def analyze(self, root: Path, relpath: str, content: str) -> AnalyzerOutput:
        relposix = Path(relpath).as_posix()
        out = AnalyzerOutput(degraded=True, diagnostics=[f"js heuristic (regex) analysis of {relposix}"])
        file_node = SemanticNode(ref=_file_ref(relpath), kind="file", name=Path(relpath).name, file=relposix)
        mod_node = SemanticNode(ref=_module_ref(relpath), kind="module", name=relposix, file=relposix)
        out.nodes += [file_node, mod_node]
        out.edges.append(SemanticEdge(file_node.ref, mod_node.ref, "contains", file=relposix))

        targets: set[str] = set()
        for rx in (_IMPORT_FROM, _IMPORT_BARE, _REQUIRE):
            targets.update(m.group(1) for m in rx.finditer(content))
        for tgt in sorted(targets):
            out.edges.append(SemanticEdge(mod_node.ref, f"module://{tgt}", "imports",
                                          resolved=False, confidence=0.6, file=relposix))

        for rx in (_FUNC, _CONST_FN):
            for m in rx.finditer(content):
                name = m.group(1)
                ref = _sym_ref(relpath, name)
                out.nodes.append(SemanticNode(ref=ref, kind="function", name=name, file=relposix))
                out.edges.append(SemanticEdge(mod_node.ref, ref, "defines", confidence=0.7, file=relposix))
        return out
