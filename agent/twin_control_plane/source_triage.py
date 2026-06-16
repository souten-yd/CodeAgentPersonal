"""Source-code triage: detect bloat (duplicate / dead code) deterministically.

The source analogue of the test triage. Two kinds of bloat are detected with no model:

- DUPLICATE  — functions that are the same logic reimplemented (same AST structure, different names).
  An AST *structure* hash (node-type shape, identifiers and literals normalized away) groups them; a
  size floor avoids matching trivial one-liners that look alike by accident.
- DEAD       — a function with NO static caller AND never executed under full-suite coverage AND not an
  entry point / public API / Protocol-or-ABC / decorated / dunder. The static call graph over-flags on
  its own (dynamic dispatch, framework-invoked handlers), so the runtime "never executed" signal and
  the exclusion rules are what make it trustworthy — the same lesson as test redundancy.

Pure and deterministic; it classifies, it does not delete or rewire. DELETE/CONSOLIDATE are decisions
for the approval-gated action plan, never applied here.
"""
from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable, Mapping

# A function smaller than this many AST nodes is too trivial to call a meaningful duplicate.
_MIN_STRUCTURE_NODES = 12


def _structure_hash(node: ast.AST) -> tuple[str, int]:
    """(hash, node_count) of a function's STRUCTURE: the sequence of AST node types, with identifiers
    and literal values normalized away so 'same logic, different names' collides while different logic
    does not."""
    parts: list[str] = []
    count = 0
    for n in ast.walk(node):
        count += 1
        parts.append(type(n).__name__)
        if isinstance(n, ast.Constant):
            parts.append(type(n.value).__name__)  # keep the literal TYPE, drop the value
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest, count


def _is_excluded_from_dead(name: str, *, decorated: bool, is_protocol_method: bool) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return True  # dunder: invoked implicitly
    if decorated:
        return True  # decorator may register/route it (FastAPI route, fixture, property, ...)
    if is_protocol_method:
        return True  # Protocol/ABC method: called via implementations
    return False


def find_duplicate_functions(file_sources: Mapping[str, str], *, min_nodes: int = _MIN_STRUCTURE_NODES) -> list[list[str]]:
    """Groups of ``py://<rel>#<qualname>`` refs that share an AST structure (candidate duplicates).
    Only non-trivial functions (>= ``min_nodes``) participate; each returned group has >1 member."""
    by_hash: dict[str, list[str]] = {}
    for rel, source in file_sources.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        def walk(node: ast.AST, prefix: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Dunders (__init__, __repr__, …) are boilerplate that is legitimately similar across
                    # classes — structurally identical but NOT reimplemented bloat — so exclude them.
                    if child.name.startswith("__") and child.name.endswith("__"):
                        continue
                    h, count = _structure_hash(child)
                    if count >= min_nodes:
                        by_hash.setdefault(h, []).append(f"py://{rel}#{prefix}{child.name}")
                elif isinstance(child, ast.ClassDef):
                    walk(child, f"{child.name}.")
        walk(tree, "")
    return [sorted(group) for group in by_hash.values() if len(group) > 1]


def find_dead_symbols(
    *,
    defined: Iterable[str],
    statically_called: Iterable[str],
    executed: Iterable[str],
    excluded: Iterable[str] = (),
) -> list[str]:
    """Symbols that are DEAD with high confidence: defined, never statically called, never executed at
    runtime, and not excluded (entry/public/Protocol/decorated/dunder — supplied by the caller). The
    combination is what avoids the static-only false positives."""
    called = {str(s) for s in statically_called}
    ran = {str(s) for s in executed}
    skip = {str(s) for s in excluded}
    out = [str(d) for d in defined if str(d) not in called and str(d) not in ran and str(d) not in skip]
    return sorted(set(out))
