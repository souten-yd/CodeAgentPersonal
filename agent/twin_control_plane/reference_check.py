"""Deterministic detection of invented project references in generated code.

A common weak-model failure is calling or importing a project symbol that does not exist — it
misremembers a name, invents a helper, or imports from the wrong module. The Twin already knows every
real symbol, so this is decidable with no model: parse the generated file, and for any
``from <project-module> import <name>`` whose ``<name>`` is not a real symbol of that module, or any
``import <project-module>`` that is not a real module, flag it. External / third-party imports are
ignored (only modules the project actually defines are checked), so there is no false-positive noise.

Pure and deterministic; returns findings the generator can act on (repair the invented reference).
"""
from __future__ import annotations

import ast
from collections.abc import Iterable


def build_symbol_index(symbol_refs: Iterable[str]) -> tuple[set[str], set[str]]:
    """From Twin source symbol refs (``py://<rel>#<qualname>``) build ``(modules, module_symbols)``.

    ``modules`` is the set of dotted module paths the project defines (e.g. ``agent.model_forge.x``);
    ``module_symbols`` is the set of ``<module>:<top_level_name>`` the project exports."""
    modules: set[str] = set()
    module_symbols: set[str] = set()
    for ref in symbol_refs:
        r = str(ref)
        if not r.startswith("py://") or "#" not in r:
            continue
        rel, _, qual = r[len("py://"):].partition("#")
        if not rel.endswith(".py"):
            continue
        dotted = rel[:-3].replace("/", ".")
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        modules.add(dotted)
        top = qual.split(".", 1)[0]
        if top:
            module_symbols.add(f"{dotted}:{top}")
    return modules, module_symbols


def check_project_references(content: str, *, modules: set[str], module_symbols: set[str]) -> list[dict]:
    """Flag invented references to PROJECT modules in ``content``. Returns
    ``[{"kind","module","name","reason"}]`` — empty when everything resolves (or there is no project
    import). Third-party/stdlib imports are ignored (their module is not in ``modules``)."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []  # a syntax error is a different failure; not ours to report

    findings: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or mod not in modules:
                continue  # relative or non-project (external) import -> not checked
            for alias in node.names:
                if alias.name == "*":
                    continue
                if f"{mod}:{alias.name}" not in module_symbols and f"{mod}.{alias.name}" not in modules:
                    findings.append({"kind": "import_from", "module": mod, "name": alias.name,
                                     "reason": f"{mod} has no symbol '{alias.name}'"})
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                # Only check names that look like project modules (a known top package prefix).
                top = name.split(".", 1)[0]
                if any(m == name or m.startswith(name + ".") for m in modules):
                    continue  # resolves to a known project module (or a package of one)
                if any(m.split(".", 1)[0] == top for m in modules) and name not in modules:
                    findings.append({"kind": "import", "module": name, "name": "",
                                     "reason": f"no project module '{name}'"})
    return findings


def render_reference_findings(findings: list[dict]) -> str:
    """Render invented-reference findings as a bounded repair directive. "" when there are none."""
    if not findings:
        return ""
    lines = ["[Invented reference check — these imports target a PROJECT module but the symbol does NOT "
             "exist. Fix each: import the correct existing name, or do not call it.]"]
    for f in findings[:12]:
        if f["kind"] == "import_from":
            lines.append(f"  - from {f['module']} import {f['name']} -> {f['reason']}")
        else:
            lines.append(f"  - import {f['module']} -> {f['reason']}")
    return "\n".join(lines)
