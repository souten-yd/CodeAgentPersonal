"""Deterministic test planning: ensure every implementation item also produces a unit test.

A weak LLM cannot be relied on to remember to write tests, so rather than hoping the planner emits
test items, this expansion DETERMINISTICALLY augments each implementation item: for every code file
it targets (e.g. ``src/calc.py``) without a matching test, it adds the unit-test path
(``src/test_calc.py``) to the item's target files and records the intent. The existing per-item
generate+verify flow then produces and runs that test. Idempotent and pure-ish (mutates the pool's
items in place and returns it). The whole-project integration (結合) check is a separate phase
(orchestrator ``run_integration_verification``).
"""
from __future__ import annotations

from pathlib import PurePosixPath


def _is_test_file(rel: str) -> bool:
    name = PurePosixPath(str(rel or "")).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def unit_test_path_for(code_rel: str) -> str:
    """``src/calc.py`` -> ``src/test_calc.py``. Returns '' for non-Python or test files."""
    p = PurePosixPath(str(code_rel or ""))
    if p.name == "" or not p.name.endswith(".py") or _is_test_file(code_rel):
        return ""
    if "/" in str(code_rel).replace("\\", "/"):
        return str(p.parent / f"test_{p.name}")
    return f"test_{p.name}"


def expand_plan_with_tests(pool):
    """For each implementation item, add a unit-test target for every code file it lacks one for, so
    generated code is always accompanied by a test. Idempotent; marks ``pool.metadata`` so reruns and
    the UI can see the expansion happened."""
    expanded = 0
    for item in (getattr(pool, "items", None) or []):
        if str(getattr(item, "item_type", "")) != "implementation":
            continue
        targets = list(getattr(item, "target_files", []) or [])
        has_test = any(_is_test_file(t) for t in targets)
        if has_test:
            continue  # the item already authors a test
        additions = []
        for code in targets:
            tp = unit_test_path_for(code)
            if tp and tp not in targets and tp not in additions:
                additions.append(tp)
        if not additions:
            continue
        item.target_files = targets + additions
        # Record intent so the generator writes the test, and verification can target it.
        note = "Also write unit tests in: " + ", ".join(additions)
        item.description = (str(getattr(item, "description", "") or "") + ("\n" if item.description else "") + note).strip()
        md = dict(getattr(item, "metadata", None) or {})
        md["unit_test_targets"] = additions
        item.metadata = md
        expanded += 1
    if expanded:
        pmd = dict(getattr(pool, "metadata", None) or {})
        pmd["test_expansion"] = {"expanded_items": expanded}
        pool.metadata = pmd
    return pool


__all__ = ["expand_plan_with_tests", "unit_test_path_for"]
