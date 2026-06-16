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
