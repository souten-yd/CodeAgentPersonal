from pathlib import Path

from agent.atlas_context_refresh_v2_schema import AtlasContextRefreshV2Request
from agent.atlas_context_refresh_v2_service import AtlasContextRefreshV2Service


def test_non_blocking_missing_plan_pool_and_index(tmp_path: Path):
    r = AtlasContextRefreshV2Service(tmp_path).refresh(AtlasContextRefreshV2Request(project_path=str(tmp_path)))
    assert r.status in {"missing", "empty_plan_pool"}
    assert r.metadata["advisory_only"] is True


def test_provided_impact_map_used_and_item_scope(tmp_path: Path):
    impact = {"status": "available", "impacts": [{"item_id": "i1", "impacted_files": ["a.py"], "related_tests": ["tests/test_a.py"], "recommended_commands": ["pytest tests/test_a.py"], "manual_verification_steps": ["check"], "ci_selection_hints": [{"k": "v"}], "reasons": ["r"], "confidence": "high"}]}
    r = AtlasContextRefreshV2Service(tmp_path).refresh(AtlasContextRefreshV2Request(project_path=str(tmp_path), item_id="i1", impact_map=impact, plan_pool={"items": [{"item_id": "i1"}]}))
    assert r.impacted_files == ["a.py"]
    assert r.related_tests == ["tests/test_a.py"]
    assert r.confidence == "high"


def test_size_limits(tmp_path: Path):
    big = [f"f{i}.py" for i in range(100)]
    impact = {"status": "available", "impacts": [{"item_id": "i1", "impacted_files": big, "related_tests": big, "recommended_commands": [str(i) for i in range(20)], "manual_verification_steps": [str(i) for i in range(20)], "ci_selection_hints": [{"i": i} for i in range(20)]}]}
    r = AtlasContextRefreshV2Service(tmp_path).refresh(AtlasContextRefreshV2Request(project_path=str(tmp_path), impact_map=impact, plan_pool={"items": [{"item_id": "i1"}]}))
    assert len(r.impacted_files) <= 50 and len(r.related_tests) <= 30 and len(r.recommended_commands) <= 5
