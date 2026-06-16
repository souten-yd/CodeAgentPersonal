"""Deterministic test triage from real test->source coverage.

Once we know which SOURCE symbols each test actually exercises (runtime coverage, ingested once and
updated incrementally), the whole test suite can be triaged with NO model — pure set/graph operations:

- IMPACTED   — tests that cover a changed symbol -> must be re-run.
- STALE       — tests whose covered symbols are ALL gone -> the code under test was removed.
- REDUNDANT   — groups of tests covering the IDENTICAL symbol set -> consolidation candidates.
- COVERAGE_GAP— source symbols no test covers -> a test should be added.

This is exact and fast (milliseconds over the coverage map), versus an LLM judging each of N tests.
An LLM is only needed for residual, genuinely-ambiguous judgment; the classifications here need none.

Pure and side-effect free: it classifies from a coverage map; it does not run tests, apply, or mutate.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from agent.twin_control_plane.twinproof import TwinProofReport


def _norm(refs: Iterable[str]) -> set[str]:
    return {str(r).strip() for r in refs if str(r).strip()}


def build_coverage_triage(
    coverage: Mapping[str, Iterable[str]],
    *,
    existing_symbols: Iterable[str],
    changed_symbols: Iterable[str] = (),
    redundancy_signatures: Mapping[str, frozenset] | None = None,
) -> TwinProofReport:
    """Classify tests from a coverage map ``{test_ref: {covered_source_symbol_ref, ...}}``.

    ``existing_symbols`` is the set of source symbols that currently exist (from the Twin graph);
    ``changed_symbols`` are the symbols touched by the change under consideration (optional — empty
    means "no specific change", so nothing is IMPACTED).

    ``redundancy_signatures`` (optional ``{test_ref: signature}``): when given, REDUNDANT is computed
    from these instead of the covered-symbol set. Pass the line-level coverage signature here — two
    tests are truly redundant only if they exercise the SAME lines, not merely the same symbol (six
    tests of one function hit different branches). Without it, redundancy falls back to symbol sets.

    Returns a TwinProofReport; feed it to ``build_test_management_plan`` for the action plan."""
    existing = _norm(existing_symbols)
    changed = _norm(changed_symbols)

    cov: dict[str, set[str]] = {}
    for test_ref, syms in coverage.items():
        t = str(test_ref).strip()
        if t:
            cov[t] = _norm(syms)

    impacted: list[str] = []
    stale: list[str] = []
    redundant: list[str] = []
    by_signature: dict[object, list[str]] = {}

    for test_ref, syms in cov.items():
        if changed and (syms & changed):
            impacted.append(test_ref)
        # Stale: the test covers at least one symbol, but NONE of them still exist.
        if syms and not (syms & existing):
            stale.append(test_ref)
        if redundancy_signatures is not None:
            sig = redundancy_signatures.get(test_ref)
            if sig:
                by_signature.setdefault(sig, []).append(test_ref)
        elif syms:
            by_signature.setdefault(frozenset(syms & existing or syms), []).append(test_ref)

    # Redundant: identical signature across >1 test -> keep one, the rest are candidates.
    for _sig, tests in by_signature.items():
        if len(tests) > 1:
            redundant.extend(sorted(tests)[1:])

    covered_syms: set[str] = set()
    for syms in cov.values():
        covered_syms |= syms
    coverage_gaps = sorted(existing - covered_syms)

    return TwinProofReport(
        report_id="coverage_triage",
        impacted_tests=sorted(set(impacted)),
        stale_candidates=sorted(set(stale)),
        redundant_candidates=sorted(set(redundant)),
        coverage_gaps=coverage_gaps,
    )
