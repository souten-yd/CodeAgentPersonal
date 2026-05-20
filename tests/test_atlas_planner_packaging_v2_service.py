from agent.atlas_planner_packaging_v2_service import AtlasPlannerPackagingV2Service
from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request

def test_service_non_blocking_and_flags(tmp_path):
    svc=AtlasPlannerPackagingV2Service(tmp_path)
    r=svc.build_package(AtlasPlannerPackagingV2Request(project_path=str(tmp_path)))
    assert r.status in {"available","partial","missing"}
    assert r.metadata["advisory_only"] is True and r.metadata["executed"] is False
    assert "ADVISORY REPOSITORY CONTEXT" in r.planner_context_text

def test_service_uses_provided_maps(tmp_path):
    svc=AtlasPlannerPackagingV2Service(tmp_path)
    r=svc.build_package(AtlasPlannerPackagingV2Request(project_path=str(tmp_path), plan_item_impact_map={"status":"available","impacts":[{"impacted_paths":["a.py"]}]}, context_refresh_v2={"status":"available","related_tests":["tests/test_a.py"],"recommended_commands":["pytest -q"],"manual_verification_steps":["check"]}))
    assert "a.py" in r.impacted_files and "tests/test_a.py" in r.related_tests
