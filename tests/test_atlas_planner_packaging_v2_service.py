from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request
from agent.atlas_planner_packaging_v2_service import AtlasPlannerPackagingV2Service
import agent.atlas_planner_packaging_v2_service as svc_mod


def test_service_impacted_files_related_tests_and_advisory_prompt(tmp_path):
    svc = AtlasPlannerPackagingV2Service(tmp_path)
    req = AtlasPlannerPackagingV2Request(
        project_path=str(tmp_path),
        plan_item_impact_map={
            'status': 'available',
            'impacts': [
                {'item_id': 'i1', 'impacted_files': ['app/main.py'], 'related_tests': ['tests/test_main.py'], 'confidence': 'high'}
            ],
        },
        context_refresh_v2={'status': 'available', 'related_tests': []},
    )
    r = svc.build_package(req)
    assert 'app/main.py' in r.impacted_files
    assert 'tests/test_main.py' in r.related_tests
    assert 'ADVISORY REPOSITORY CONTEXT' in r.planner_context_text
    assert 'DO NOT EXECUTE' in r.planner_context_text
    assert 'manual-only' in r.planner_context_text
    assert 'app/main.py' in r.planner_context_text
    assert 'tests/test_main.py' in r.planner_context_text


def test_service_safety_flags(tmp_path):
    r = AtlasPlannerPackagingV2Service(tmp_path).build_package(AtlasPlannerPackagingV2Request(project_path=str(tmp_path)))
    m = r.metadata
    assert m['advisory_only'] is True
    assert m['executed'] is False
    assert m['shell_executed'] is False
    assert m['remote_git_executed'] is False
    assert m['auto_verification_triggered'] is False
    assert m['auto_test_execution_triggered'] is False
    assert m['no_auto_build'] is True
    assert m['no_execution'] is True
    assert m['commands_are_suggestions_only'] is True
    assert m['planner_packaging_v2'] is True


def test_service_builder_failures_non_blocking(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(svc_mod.AtlasRepoContextPlannerPackager, 'build_package', boom)
    monkeypatch.setattr(svc_mod.AtlasPlanItemImpactMapService, 'build_map', boom)
    monkeypatch.setattr(svc_mod.AtlasContextRefreshV2Service, 'refresh', boom)

    req = AtlasPlannerPackagingV2Request(project_path=str(tmp_path), include_repo_context=True, include_plan_item_impact_map=True, include_context_refresh_v2=True, plan_pool={'items':[]})
    r = AtlasPlannerPackagingV2Service(tmp_path).build_package(req)
    assert r.status in {'partial', 'missing'}
    assert 'repo_context_unavailable' in r.warnings
    assert 'plan_item_impact_map_unavailable' in r.warnings
    assert 'context_refresh_v2_unavailable' in r.warnings
