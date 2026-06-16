"""Input/output signature of a test, for deterministic redundancy without a model.

Line coverage over-flags redundancy: six tests that all execute the same function look identical even
though they pass different inputs and assert different outputs (decimal GB vs kHz). The fix, with no
model, is to look at what each test actually feeds in and checks — its INPUT/OUTPUT literals. Two tests
are redundant only if they have the SAME I/O signature (same literal arguments AND same asserted
values); different inputs or outputs mean they guard different regressions.

This extracts that signature deterministically from the test AST: the set of literal constants
(strings / numbers / bools) the test uses, which captures both the inputs it passes and the outputs it
asserts. Pure; no execution, no model.
"""
from __future__ import annotations

import ast


def _literals(node: ast.AST) -> set:
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, (str, int, float, bool)):
            # tag with type so 1 (int) and "1" (str) don't collide.
            out.add((type(n.value).__name__, n.value))
    return out


def io_signatures_for_source(source: str, *, prefix: str = "") -> dict[str, frozenset]:
    """``{test_ref: frozenset(io_literals)}`` for every ``test_*`` function in a test file source.

    ``prefix`` (e.g. ``py://tests/test_x.py#``) is prepended to each test name so the keys match the
    coverage map. A test with no literals gets an empty signature (it falls back to other signals)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    sigs: dict[str, frozenset] = {}

    def visit(container: ast.AST, name_prefix: str) -> None:
        for child in ast.iter_child_nodes(container):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test"):
                sigs[f"{prefix}{name_prefix}{child.name}"] = frozenset(_literals(child))
            elif isinstance(child, ast.ClassDef) and child.name.startswith("Test"):
                visit(child, f"{name_prefix}{child.name}.")

    visit(tree, "")
    return sigs


def io_signatures_for_files(file_to_source: dict[str, str]) -> dict[str, frozenset]:
    """Merge I/O signatures across files. ``file_to_source`` maps a repo-relative test path (e.g.
    ``tests/test_x.py``) to its source; keys come out as ``py://<path>#<test>`` to match coverage."""
    out: dict[str, frozenset] = {}
    for rel, source in file_to_source.items():
        out.update(io_signatures_for_source(source, prefix=f"py://{rel}#"))
    return out
