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


def find_duplicate_symbols_from_twin(store, project_id: str, *, mode: str = "exact", min_nodes: int = _MIN_STRUCTURE_NODES) -> list[list[str]]:
    """Native Twin query for duplicate functions, using the ``structure_hash`` / ``body_hash`` the static
    analyzer now stores on each function/method node. ``mode="exact"`` (body_hash) returns
    behavior-identical groups safe to auto-consolidate; ``mode="structure"`` (structure_hash) returns
    same-shape candidates that need a judgment call. Dunders excluded. No source re-parsing — the Twin
    already computed the fingerprints at build time, so this is incremental and queryable."""
    key = "body_hash" if mode == "exact" else "structure_hash"
    try:
        snapshot = store.get_snapshot(project_id)
    except Exception:
        return []
    by_hash: dict[str, list[str]] = {}
    for node in getattr(snapshot, "nodes", []) or []:
        if getattr(node, "node_type", "") not in ("function", "method"):
            continue
        ref = str(getattr(node, "canonical_ref", ""))
        name = ref.rsplit("#", 1)[-1].rsplit(".", 1)[-1]
        if name.startswith("__") and name.endswith("__"):
            continue
        props = getattr(node, "properties", {}) or {}
        h = props.get(key)
        try:
            if not h or int(props.get("node_count", 0)) < min_nodes:
                continue
        except (TypeError, ValueError):
            continue
        by_hash.setdefault(str(h), []).append(ref)
    return [sorted(set(g)) for g in by_hash.values() if len(set(g)) > 1]


def _body_hash(node: ast.AST) -> tuple[str, int]:
    """(hash, node_count) of a function's EXACT body: ``ast.dump`` of the statements, identifiers and
    literals INCLUDED. Two functions with the same body hash are behavior-identical (the function name
    aside), so merging them is provably safe — the only duplicates a machine may consolidate without a
    judgment call."""
    try:
        dumped = "||".join(ast.dump(s) for s in getattr(node, "body", []))
    except Exception:
        dumped = ""
    count = sum(1 for _ in ast.walk(node))
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16], count


def find_exact_duplicate_functions(file_sources: Mapping[str, str], *, min_nodes: int = _MIN_STRUCTURE_NODES) -> list[list[str]]:
    """Groups of functions with an IDENTICAL body (not just structure). Unlike find_duplicate_functions
    (which finds candidates that may be semantically distinct, e.g. DI providers of the same shape),
    these are behavior-identical and SAFE to consolidate mechanically — verify with tests, revert on
    failure. Dunders excluded; trivial functions below ``min_nodes`` excluded."""
    by_body: dict[str, list[str]] = {}
    for rel, source in file_sources.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        def walk(node: ast.AST, prefix: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("__") and child.name.endswith("__"):
                        continue
                    h, count = _body_hash(child)
                    if count >= min_nodes:
                        by_body.setdefault(h, []).append(f"py://{rel}#{prefix}{child.name}")
                elif isinstance(child, ast.ClassDef):
                    walk(child, f"{child.name}.")
        walk(tree, "")
    return [sorted(g) for g in by_body.values() if len(g) > 1]


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
