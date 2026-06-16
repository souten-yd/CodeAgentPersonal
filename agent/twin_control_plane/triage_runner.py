"""End-to-end deterministic test-triage runner.

Ties the pieces together: ingest real per-test coverage (``coverage_ingest``), read the set of source
symbols that currently exist from the Twin, then classify the suite (``coverage_triage``) and produce
the approval-gated action plan (``test_management``). No model — the whole triage is deterministic and
sub-second once coverage exists. ``changed_files`` narrows IMPACTED (re-run) to a specific change.

This is the capstone for "triage the test suite with the Twin": run it after collecting coverage
(``pytest --cov --cov-context=test``) to get re-run / retire-stale / consolidate-redundant /
add-coverage as a single plan.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _existing_source_symbols(store, project_id: str, prefixes: tuple[str, ...]) -> set[str]:
    """Source symbol refs (function/method/class) that currently exist in the Twin graph."""
    try:
        snapshot = store.get_snapshot(project_id)
    except Exception:
        return set()
    out: set[str] = set()
    for node in getattr(snapshot, "nodes", []) or []:
        ref = str(getattr(node, "canonical_ref", ""))
        if getattr(node, "node_type", "") in ("function", "method", "class") and ref.startswith("py://"):
            if "#" in ref and any(ref[len("py://"):].startswith(p) for p in prefixes):
                out.add(ref)
    return out


def _io_signatures_for_tests(test_refs: Iterable[str], repo_root: str) -> dict[str, frozenset]:
    """Build I/O signatures for the test files referenced in the coverage map (read once each)."""
    from agent.twin_control_plane.test_signature import io_signatures_for_files

    files: dict[str, str] = {}
    for ref in test_refs:
        r = str(ref)
        if not r.startswith("py://") or "#" not in r:
            continue
        rel = r[len("py://"):].split("#", 1)[0]
        if rel in files:
            continue
        try:
            files[rel] = (Path(repo_root) / rel).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return io_signatures_for_files(files)


def run_test_triage(
    *,
    coverage_data_file: str,
    repo_root: str,
    store,
    project_id: str,
    changed_files: Iterable[str] = (),
    source_prefixes: tuple[str, ...] = ("agent/", "app/"),
):
    """Run the deterministic triage. Returns ``{"report", "plan", "coverage_tests", "existing_symbols"}``.

    ``report`` is a TwinProofReport (impacted/stale/redundant/coverage_gaps); ``plan`` is the
    approval-gated TestManagementPlan. Never raises beyond import errors from coverage_ingest."""
    from agent.twin_control_plane.coverage_ingest import build_coverage_map
    from agent.twin_control_plane.coverage_triage import build_coverage_triage
    from agent.twin_control_plane.test_management import build_test_management_plan

    symbol_map, _line_sig = build_coverage_map(coverage_data_file, repo_root, include_prefixes=source_prefixes)
    existing = _existing_source_symbols(store, project_id, source_prefixes)
    # REDUNDANCY by INPUT/OUTPUT signature, not line coverage: two tests are redundant only if they feed
    # the same inputs and assert the same outputs. Line coverage over-flags parametric tests (same code
    # path, different data); the I/O signature distinguishes them deterministically (no model).
    io_sig = _io_signatures_for_tests(symbol_map.keys(), repo_root)

    changed_symbols: set[str] = set()
    files = [str(f).strip() for f in changed_files if str(f).strip()]
    if files:
        try:
            from agent.twin_control_plane.pipeline_integration import expand_changed_refs_to_symbols
            for ref in expand_changed_refs_to_symbols(store, project_id, files):
                if ref.startswith("py://") and "#" in ref:
                    changed_symbols.add(ref)
        except Exception:
            pass

    report = build_coverage_triage(
        symbol_map, existing_symbols=existing, changed_symbols=changed_symbols,
        redundancy_signatures=io_sig)
    plan = build_test_management_plan(report)
    return {
        "report": report,
        "plan": plan,
        "coverage_tests": len(symbol_map),
        "existing_symbols": len(existing),
    }


def collect_coverage(test_paths: Iterable[str], *, repo_root: str, data_file: str, source_prefixes=("agent", "app")) -> int:
    """Run pytest with per-test coverage contexts and write ``data_file``. Returns the pytest exit code.

    Heavy (it runs the tests), intended for a one-time/CI collection or an incremental subset; the
    triage itself is sub-second over the resulting data file."""
    import subprocess
    import sys

    cov_args = []
    for p in source_prefixes:
        cov_args.append(f"--cov={p}")
    cmd = [sys.executable, "-m", "pytest", *list(test_paths), *cov_args,
           "--cov-context=test", "--cov-report=", "-q", "-p", "no:cacheprovider"]
    env = {"COVERAGE_FILE": str(data_file)}
    import os
    full_env = {**os.environ, **env, "PYTHONPATH": repo_root}
    proc = subprocess.run(cmd, cwd=repo_root, env=full_env, check=False)
    return proc.returncode
