"""Coverage ingest: map covered (file, line) to Twin symbols.

The pure mapping functions are tested directly (no coverage.py needed); build_coverage_map (which reads
a coverage.py data file) is exercised by the live triage evaluation and skipped here when coverage is
not importable.
"""
from __future__ import annotations

import pytest

from agent.twin_control_plane.coverage_ingest import (
    _enclosing, _normalize_test_ref, symbol_ranges,
)

SRC = '''\
def foo():
    return 1


class Bar:
    def baz(self):
        return 2

    def qux(self):
        return 3
'''


def test_symbol_ranges_covers_functions_methods_and_classes():
    ranges = symbol_ranges("mod.py", SRC)
    refs = {r for r, _s, _e in ranges}
    assert "py://mod.py#foo" in refs
    assert "py://mod.py#Bar" in refs
    assert "py://mod.py#Bar.baz" in refs
    assert "py://mod.py#Bar.qux" in refs


def test_enclosing_picks_innermost_symbol():
    ranges = symbol_ranges("mod.py", SRC)
    assert _enclosing(ranges, 2) == "py://mod.py#foo"          # inside foo
    assert _enclosing(ranges, 6) == "py://mod.py#Bar.baz"      # inside the method, not just the class
    assert _enclosing(ranges, 10) == "py://mod.py#Bar.qux"
    assert _enclosing(ranges, 100) == ""                        # no symbol on that line


def test_normalize_test_ref_from_coverage_context():
    assert _normalize_test_ref("tests/test_x.py::test_fn|run") == "py://tests/test_x.py#test_fn"
    assert _normalize_test_ref("tests/test_x.py::TestC::test_m|run") == "py://tests/test_x.py#TestC.test_m"
    assert _normalize_test_ref("") == ""


def test_build_coverage_map_importable_or_skips():
    pytest.importorskip("coverage")
    from agent.twin_control_plane.coverage_ingest import build_coverage_map
    assert callable(build_coverage_map)
