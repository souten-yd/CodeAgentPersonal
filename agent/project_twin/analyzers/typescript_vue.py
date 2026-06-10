"""TypeScript and Vue basic semantic analyzer (PI-6).

Heuristic extraction of imports, TS interfaces/classes, and Vue single-file-component
basics (component node + script imports). Heuristic facts carry confidence < 1.0.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent.project_twin.analyzers.registry import AnalyzerCapability, AnalyzerOutput
from agent.project_twin.graph.semantic import SemanticEdge, SemanticNode

_VERSION = "tsvue-sem-2.0"
_CAPS = frozenset({"modules", "imports", "interfaces", "components"})

_IMPORT_FROM = re.compile(r"""import\s+(?:[\w*\s{},]+?)\s+from\s+['"]([^'"]+)['"]""")
_INTERFACE = re.compile(r"""^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)""", re.M)
_CLASS = re.compile(r"""^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)""", re.M)
_SCRIPT_BLOCK = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)
_TEMPLATE_BLOCK = re.compile(r"<template[^>]*>", re.I)


def _file_ref(relpath: str) -> str:
    return f"file://{Path(relpath).as_posix()}"


def _module_ref(relpath: str) -> str:
    return f"module://{Path(relpath).as_posix()}"


class TypeScriptVueAnalyzer:
    suffixes = (".ts", ".tsx", ".vue")

    def capability(self) -> AnalyzerCapability:
        return AnalyzerCapability(language="typescript_vue", version=_VERSION, capabilities=_CAPS)

    def analyze(self, root: Path, relpath: str, content: str) -> AnalyzerOutput:
        relposix = Path(relpath).as_posix()
        is_vue = Path(relpath).suffix.lower() == ".vue"
        out = AnalyzerOutput(degraded=True,
                             diagnostics=[f"{'vue' if is_vue else 'ts'} heuristic analysis of {relposix}"])
        file_node = SemanticNode(ref=_file_ref(relpath), kind="file", name=Path(relpath).name, file=relposix)
        mod_node = SemanticNode(ref=_module_ref(relpath), kind="module", name=relposix, file=relposix)
        out.nodes += [file_node, mod_node]
        out.edges.append(SemanticEdge(file_node.ref, mod_node.ref, "contains", file=relposix))

        script = content
        if is_vue:
            blocks = _SCRIPT_BLOCK.findall(content)
            script = "\n".join(blocks)
            comp_name = Path(relpath).stem
            comp_ref = f"vue://{relposix}#{comp_name}"
            out.nodes.append(SemanticNode(ref=comp_ref, kind="component", name=comp_name, file=relposix,
                                          properties={"has_template": bool(_TEMPLATE_BLOCK.search(content))}))
            out.edges.append(SemanticEdge(mod_node.ref, comp_ref, "defines", confidence=0.8, file=relposix))

        for tgt in sorted({m.group(1) for m in _IMPORT_FROM.finditer(script)}):
            out.edges.append(SemanticEdge(mod_node.ref, f"module://{tgt}", "imports",
                                          resolved=False, confidence=0.6, file=relposix))
        for rx, kind in ((_INTERFACE, "type"), (_CLASS, "class")):
            for m in rx.finditer(script):
                name = m.group(1)
                ref = f"js://{relposix}#{name}"
                out.nodes.append(SemanticNode(ref=ref, kind=kind, name=name, file=relposix))
                out.edges.append(SemanticEdge(mod_node.ref, ref, "defines", confidence=0.7, file=relposix))
        return out
