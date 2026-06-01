from __future__ import annotations

from agent.atlas_plan_depth_gate import evaluate_plan_depth
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _item(item_id, *, item_type="implementation", target_files=None, description="", goal=""):
    return AtlasPlanItem(
        item_id=item_id, pool_id="p1", title="t", goal=goal, description=description,
        item_type=item_type, status="ready", risk_level="low",
        target_files=target_files if target_files is not None else ["src/x.py"],
    )


def _pool(items):
    return AtlasPlanPool(pool_id="p1", root_goal="g", items=items)


def test_substantive_plan_passes():
    item = _item("i1", target_files=["src/a.py"], description="Implement the wave animation render loop and timing")
    out = evaluate_plan_depth(_pool([item]))
    assert out["ok"] is True
    assert out["reasons"] == []


def test_no_implementation_items_blocks():
    out = evaluate_plan_depth(_pool([_item("i1", item_type="research")]))
    assert out["ok"] is False
    assert "no_implementation_items" in out["reasons"]


def test_missing_target_files_flagged():
    item = _item("i1", target_files=[], description="A sufficiently long description of the work to do")
    out = evaluate_plan_depth(_pool([item]))
    assert out["ok"] is False
    assert "item_missing_target_files:i1" in out["reasons"]


def test_shallow_description_flagged():
    item = _item("i1", target_files=["src/a.py"], description="fix")
    out = evaluate_plan_depth(_pool([item]))
    assert out["ok"] is False
    assert "item_description_too_shallow:i1" in out["reasons"]
