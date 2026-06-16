"""Ingest real per-test runtime coverage into a Twin-symbol coverage map.

This is the data source that makes the deterministic triage (``coverage_triage``) accurate: it reads a
coverage.py data file collected with per-test contexts (``pytest --cov --cov-context=test``) and maps
each covered (file, line) to the enclosing Twin source symbol (``py://<relpath>#<symbol>``), yielding
``{test_ref: {covered_source_symbol}}``.

Two granularities are produced:
- symbol coverage -> IMPACTED / STALE / COVERAGE_GAP (which source symbols a test exercises);
- line-signature  -> REDUNDANT (two tests are redundant only if they exercise the SAME lines, not just
  the same symbol — six tests of one function hit different branches, so their line sets differ).

Pure parsing; no test execution here. Requires ``coverage`` to be importable to read the data file.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path


def symbol_ranges(rel_posix: str, source: str) -> list[tuple[str, int, int]]:
    """(``py://<rel>#<qualname>``, start_line, end_line) for every function/method/class in a file."""
    out: list[tuple[str, int, int]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                start = child.lineno
                end = getattr(child, "end_lineno", None) or start
                out.append((f"py://{rel_posix}#{name}", start, end))
                if isinstance(child, ast.ClassDef):
                    walk(child, f"{name}.")
    walk(tree, "")
    return out


def _enclosing(ranges: list[tuple[str, int, int]], line: int) -> str:
    """Innermost symbol whose [start,end] contains ``line`` (last match wins = most specific)."""
    hit = ""
    for ref, start, end in ranges:
        if start <= line <= end:
            hit = ref  # ranges are emitted outer-then-inner, so the last container is the most specific
    return hit


def _normalize_test_ref(context: str) -> str:
    """``tests/test_x.py::test_fn|run`` (coverage context) -> ``py://tests/test_x.py#test_fn``."""
    ctx = str(context or "").split("|", 1)[0].strip()
    if "::" in ctx:
        path, _, name = ctx.partition("::")
        name = name.replace("::", ".")
        return f"py://{path.replace(os.sep, '/')}#{name}"
    return ctx


def build_coverage_map(data_file: str, repo_root: str, *, include_prefixes: tuple[str, ...] = ("agent/", "app/")):
    """Return ``(symbol_map, line_signature)`` from a coverage.py data file with test contexts.

    ``symbol_map``: ``{test_ref: {covered_source_symbol_ref}}``.
    ``line_signature``: ``{test_ref: frozenset((rel, line))}`` for redundancy at line granularity.
    Never raises beyond import errors; files that fail to parse are skipped."""
    import coverage  # local import: optional dependency

    root = Path(repo_root).resolve()
    cov = coverage.Coverage(data_file=data_file)
    cov.load()
    data = cov.get_data()

    symbol_map: dict[str, set[str]] = {}
    line_sig: dict[str, set[tuple[str, int]]] = {}
    ranges_cache: dict[str, list[tuple[str, int, int]]] = {}

    for fpath in data.measured_files():
        try:
            rel = Path(fpath).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if not rel.endswith(".py") or not any(rel.startswith(p) for p in include_prefixes):
            continue
        if rel not in ranges_cache:
            try:
                ranges_cache[rel] = symbol_ranges(rel, Path(fpath).read_text(encoding="utf-8", errors="replace"))
            except Exception:
                ranges_cache[rel] = []
        ranges = ranges_cache[rel]
        try:
            by_line = data.contexts_by_lineno(fpath)
        except Exception:
            continue
        for line, contexts in by_line.items():
            sym = _enclosing(ranges, line)
            for ctx in contexts:
                if not ctx:
                    continue
                test_ref = _normalize_test_ref(ctx)
                line_sig.setdefault(test_ref, set()).add((rel, line))
                if sym:
                    symbol_map.setdefault(test_ref, set()).add(sym)
    return symbol_map, {t: frozenset(s) for t, s in line_sig.items()}
