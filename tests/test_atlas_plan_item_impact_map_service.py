from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMapRequest
from agent.atlas_plan_item_impact_map_service import AtlasPlanItemImpactMapService


def _req(tmp_path, plan_pool=None):
    return AtlasPlanItemImpactMapRequest(project_path=str(tmp_path), changed_files=["app/a.py"], target_files=["app/a.py"], plan_pool=plan_pool or {})


def test_empty_plan_pool_non_blocking(tmp_path):
    out = AtlasPlanItemImpactMapService(tmp_path).build_map(_req(tmp_path, {}))
    assert out.status in {"missing", "empty_plan_pool"}


def test_one_entry_per_item(tmp_path):
    pool = {"items": [{"item_id": "1", "title": "t1", "target_files": ["app/a.py"]}, {"item_id": "2", "title": "t2", "target_files": ["app/b.py"]}]}
    out = AtlasPlanItemImpactMapService(tmp_path).build_map(_req(tmp_path, pool))
    assert out.item_count == 2 and len(out.impacts) == 2
    assert out.metadata["executed"] is False


def test_limits_and_confidence_and_flags(tmp_path):
    pool = {"items": [{"item_id": "1", "target_files": ["x/y.py"], "metadata": {"repo_context": {"impacted_symbols": [str(i) for i in range(80)]}}}]}
    out = AtlasPlanItemImpactMapService(tmp_path).build_map(_req(tmp_path, pool))
    i = out.impacts[0]
    assert len(i.impacted_symbols) <= 30
    assert len(i.recommended_commands) <= 5
    assert i.confidence in {"high", "medium", "low", "unknown"}
    assert i.metadata["auto_test_execution_triggered"] is False
