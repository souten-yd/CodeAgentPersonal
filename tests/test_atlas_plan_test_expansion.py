"""Deterministic test planning: every implementation item gains a unit-test target."""
from __future__ import annotations

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_test_expansion import expand_plan_with_tests, unit_test_path_for


def test_unit_test_path_for():
    assert unit_test_path_for("src/calc.py") == "src/test_calc.py"
    assert unit_test_path_for("calc.py") == "test_calc.py"
    assert unit_test_path_for("src/test_calc.py") == ""   # already a test
    assert unit_test_path_for("README.md") == ""           # not python


def _pool(items):
    return AtlasPlanPool(pool_id="p", root_goal="g", project_path="/tmp/p", items=items)


def test_expands_implementation_item_with_unit_test():
    item = AtlasPlanItem(item_id="i1", pool_id="p", title="t", goal="add subtract",
                         item_type="implementation", target_files=["src/calc.py"])
    pool = expand_plan_with_tests(_pool([item]))
    it = pool.items[0]
    assert "src/test_calc.py" in it.target_files
    assert it.metadata.get("unit_test_targets") == ["src/test_calc.py"]
    assert pool.metadata.get("test_expansion", {}).get("expanded_items") == 1


def test_idempotent_when_test_already_present():
    item = AtlasPlanItem(item_id="i1", pool_id="p", title="t", goal="g",
                         item_type="implementation", target_files=["src/calc.py", "src/test_calc.py"])
    pool = expand_plan_with_tests(_pool([item]))
    assert pool.items[0].target_files == ["src/calc.py", "src/test_calc.py"]  # unchanged
    assert "test_expansion" not in (pool.metadata or {})


def test_non_implementation_items_untouched():
    item = AtlasPlanItem(item_id="i1", pool_id="p", title="t", goal="g",
                         item_type="documentation", target_files=["docs/x.py"])
    pool = expand_plan_with_tests(_pool([item]))
    assert pool.items[0].target_files == ["docs/x.py"]
