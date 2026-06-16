"""Relevance-ranked symbol selection for generation context.

On a large repo the arbitrary first-N symbols are mostly irrelevant. With relevance_terms, the most
relevant symbols must surface within the cap. Negative control: without terms, behavior is unchanged
(first-N in scan order).
"""
from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.adapters.code_explorer import extract_symbols


def _mk(tmp_path: Path):
    # Many files so the relevant symbol would fall outside an unranked first-N cap.
    for i in range(40):
        (tmp_path / f"mod_{i:02d}.py").write_text(f"def unrelated_{i}():\n    return {i}\n", encoding="utf-8")
    (tmp_path / "collision.py").write_text(
        "def check_collision(a, b):\n    '''detect collision between sprites'''\n    return a == b\n",
        encoding="utf-8")
    return tmp_path


def test_relevance_terms_surface_the_matching_symbol(tmp_path):
    _mk(tmp_path)
    ranked = extract_symbols(str(tmp_path), max_symbols=5, relevance_terms=["collision", "detect"])
    names = [s["name"] for s in ranked]
    assert "check_collision" in names  # surfaced despite being one of 41 files
    assert names[0] == "check_collision"  # ranked first


def test_target_file_symbols_are_boosted(tmp_path):
    _mk(tmp_path)
    ranked = extract_symbols(str(tmp_path), max_symbols=3, relevance_terms=["collision"])
    assert ranked[0]["file"] == "collision.py"


def test_without_terms_behavior_unchanged(tmp_path):
    _mk(tmp_path)
    a = extract_symbols(str(tmp_path), max_symbols=5)
    b = extract_symbols(str(tmp_path), max_symbols=5)
    assert a == b  # deterministic, unranked
    assert len(a) == 5


def test_target_files_scoping_ignores_relevance(tmp_path):
    # When target_files is given we scan only those (no whole-project ranking).
    _mk(tmp_path)
    syms = extract_symbols(str(tmp_path), target_files=["collision.py"], relevance_terms=["unrelated"])
    assert {s["file"] for s in syms} == {"collision.py"}
