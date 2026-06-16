"""Budget-based, per-symbol adaptive impact depth.

Fan-out varies per symbol: a hub over-expands at shallow depth, a leaf can be explored deep. The
budget search grows depth from 1 and keeps the deepest result whose dependent set still fits the
context budget. These tests use a stub store with a known size-per-depth curve.
"""
from __future__ import annotations

from types import SimpleNamespace

from agent.twin_control_plane.pipeline_integration import assess_impact_within_budget


class _StubStore:
    """assess_impact returns `sizes[depth]` dependents (split across direct/transitive)."""
    def __init__(self, sizes_by_depth: dict[int, int]):
        self.sizes = sizes_by_depth
        self.calls: list[int] = []

    def assess_impact(self, request):
        self.calls.append(request.max_depth)
        n = self.sizes.get(request.max_depth, self.sizes.get(max(self.sizes), 0))
        items = [SimpleNamespace(canonical_ref=f"py://d{request.max_depth}_{i}.py#x", confidence=1.0)
                 for i in range(n)]
        return SimpleNamespace(direct_impacts=items[:1], transitive_impacts=items[1:])


def _size(imp):
    return len(imp.direct_impacts) + len(imp.transitive_impacts)


def test_stops_at_depth_before_budget_overflow():
    # depth: 1->5, 2->20, 3->90 (overflow at budget 60) -> keep depth 2 (20).
    store = _StubStore({1: 5, 2: 20, 3: 90, 4: 90})
    imp = assess_impact_within_budget(store, "p", ["py://m.py#f"], budget=60, max_depth=6)
    assert _size(imp) == 20
    assert store.calls[:3] == [1, 2, 3]  # grew until depth 3 overflowed


def test_leaf_with_low_fanout_goes_deep():
    # A leaf: small at every depth, reaches a fixpoint -> explores deep, returns the converged set.
    store = _StubStore({1: 2, 2: 4, 3: 4, 4: 4})
    imp = assess_impact_within_budget(store, "p", ["py://m.py#leaf"], budget=60, max_depth=6)
    assert _size(imp) == 4


def test_hub_overflowing_at_depth1_returns_depth1():
    store = _StubStore({1: 500, 2: 900})
    imp = assess_impact_within_budget(store, "p", ["py://m.py#hub"], budget=60, max_depth=6)
    assert _size(imp) == 500
    assert store.calls == [1]  # stopped immediately
