"""End-to-end triage runner + line-level redundancy."""
from __future__ import annotations

from types import SimpleNamespace

from agent.twin_control_plane.coverage_triage import build_coverage_triage


def test_line_signatures_override_symbol_redundancy():
    # Two tests cover the SAME symbol but DIFFERENT lines -> NOT redundant with line signatures.
    coverage = {"test://a": ["py://m.py#f"], "test://b": ["py://m.py#f"]}
    line_sig = {"test://a": frozenset({("m.py", 1)}), "test://b": frozenset({("m.py", 2)})}
    # Without line sigs: symbol-redundant.
    r_sym = build_coverage_triage(coverage, existing_symbols=["py://m.py#f"])
    assert r_sym.redundant_candidates == ["test://b"]
    # With line sigs: distinct lines -> not redundant.
    r_line = build_coverage_triage(coverage, existing_symbols=["py://m.py#f"], redundancy_signatures=line_sig)
    assert r_line.redundant_candidates == []
    # Identical line sigs -> redundant again.
    same = {"test://a": frozenset({("m.py", 1)}), "test://b": frozenset({("m.py", 1)})}
    r_same = build_coverage_triage(coverage, existing_symbols=["py://m.py#f"], redundancy_signatures=same)
    assert r_same.redundant_candidates == ["test://b"]


class _StubStore:
    def __init__(self, refs):
        self._nodes = [SimpleNamespace(canonical_ref=r, node_type="function") for r in refs]
    def get_snapshot(self, project_id):
        return SimpleNamespace(nodes=self._nodes, edges=[])


def test_existing_source_symbols_filters_to_source():
    from agent.twin_control_plane.triage_runner import _existing_source_symbols
    store = _StubStore(["py://agent/m.py#f", "py://tests/test_m.py#t", "py://app/x.py#g"])
    got = _existing_source_symbols(store, "p", ("agent/", "app/"))
    assert got == {"py://agent/m.py#f", "py://app/x.py#g"}  # tests/ excluded
