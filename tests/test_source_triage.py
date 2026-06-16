"""Source-code triage: deterministic duplicate / dead-code detection."""
from __future__ import annotations

from agent.twin_control_plane.source_triage import find_duplicate_functions, find_dead_symbols


def test_same_logic_different_names_is_grouped():
    a = "def is_valid_a(x):\n    return x in {'p','q','r'} and len(x) > 0 and bool(x)\n"
    b = "def is_valid_b(y):\n    return y in {'m','n','o'} and len(y) > 0 and bool(y)\n"
    groups = find_duplicate_functions({"a.py": a, "b.py": b}, min_nodes=8)
    assert any({"py://a.py#is_valid_a", "py://b.py#is_valid_b"} <= set(g) for g in groups)


def test_different_logic_not_grouped():
    a = "def f(x):\n    total = 0\n    for i in x:\n        total += i\n    return total\n"
    b = "def g(x):\n    return [i for i in x if i > 0]\n"
    assert find_duplicate_functions({"a.py": a, "b.py": b}, min_nodes=6) == []


def test_dunders_excluded():
    a = "class A:\n    def __init__(self, x):\n        self.x = x\n        self.y = x + 1\n        self.z = x * 2\n"
    b = "class B:\n    def __init__(self, x):\n        self.x = x\n        self.y = x + 1\n        self.z = x * 2\n"
    assert find_duplicate_functions({"a.py": a, "b.py": b}, min_nodes=4) == []  # __init__ not flagged


def test_trivial_functions_below_threshold_ignored():
    a = "def f():\n    return 1\n"
    b = "def g():\n    return 2\n"
    assert find_duplicate_functions({"a.py": a, "b.py": b}) == []  # too small


def test_dead_requires_no_caller_and_not_executed_and_not_excluded():
    dead = find_dead_symbols(
        defined=["py://m.py#used", "py://m.py#called_only", "py://m.py#ran_only",
                 "py://m.py#excluded", "py://m.py#truly_dead"],
        statically_called=["py://m.py#used", "py://m.py#called_only"],
        executed=["py://m.py#used", "py://m.py#ran_only"],
        excluded=["py://m.py#excluded"],
    )
    assert dead == ["py://m.py#truly_dead"]  # only the one that is none of called/ran/excluded


def test_exact_body_duplicates_are_behavior_identical():
    from agent.twin_control_plane.source_triage import find_exact_duplicate_functions
    # Same body, different name -> exact duplicate (safe to merge).
    a = "def utc_a():\n    return datetime.now(timezone.utc).isoformat() + 'x' + str(1)\n"
    b = "def utc_b():\n    return datetime.now(timezone.utc).isoformat() + 'x' + str(1)\n"
    # Same STRUCTURE but different body (literal differs) -> NOT an exact duplicate.
    c = "def utc_c():\n    return datetime.now(timezone.utc).isoformat() + 'y' + str(2)\n"
    groups = find_exact_duplicate_functions({"a.py": a, "b.py": b, "c.py": c}, min_nodes=6)
    flat = {r for g in groups for r in g}
    assert "py://a.py#utc_a" in flat and "py://b.py#utc_b" in flat
    assert "py://c.py#utc_c" not in flat  # different body -> not auto-mergeable


def test_twin_native_duplicate_query_uses_node_fingerprints():
    from types import SimpleNamespace
    from agent.twin_control_plane.source_triage import find_duplicate_symbols_from_twin

    def fn(ref, body_h, struct_h, nc=20, dec=False):
        nm = ref.rsplit("#", 1)[-1]
        return SimpleNamespace(canonical_ref=ref, node_type="function",
                               properties={"body_hash": body_h, "structure_hash": struct_h,
                                           "node_count": nc, "decorated": dec})
    nodes = [
        fn("py://a.py#f", "BODY1", "SHAPE1"),
        fn("py://b.py#g", "BODY1", "SHAPE1"),     # identical body -> exact dup of f
        fn("py://c.py#h", "BODY2", "SHAPE1"),     # same shape, different body
        fn("py://d.py#__init__", "BODY1", "SHAPE1"),  # dunder -> excluded
        fn("py://e.py#small", "BODY1", "SHAPE1", nc=4),  # below min_nodes -> excluded
    ]
    store = SimpleNamespace(get_snapshot=lambda pid: SimpleNamespace(nodes=nodes, edges=[]))

    exact = find_duplicate_symbols_from_twin(store, "p", mode="exact", min_nodes=10)
    assert exact == [["py://a.py#f", "py://b.py#g"]]  # only the identical-body pair, no dunder/small
    structure = find_duplicate_symbols_from_twin(store, "p", mode="structure", min_nodes=10)
    assert any({"py://a.py#f", "py://b.py#g", "py://c.py#h"} <= set(g) for g in structure)
