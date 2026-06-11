from pathlib import Path

from agent.atlas_context_refresh_v2_schema import AtlasContextRefreshV2Request
from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMap
from agent.project_intelligence.adapters.context_refresh_v2 import ProjectIntelligenceContextRefreshV2Adapter


def test_non_blocking_missing_plan_pool_and_index(tmp_path: Path):
    r = ProjectIntelligenceContextRefreshV2Adapter(tmp_path).refresh(
        AtlasContextRefreshV2Request(project_path=str(tmp_path))
    )
    assert r.status in {'missing', 'empty_plan_pool'}
    assert r.metadata['advisory_only'] is True


def test_impact_map_build_failure_non_blocking(tmp_path: Path, monkeypatch):
    svc = ProjectIntelligenceContextRefreshV2Adapter(tmp_path)
    monkeypatch.setattr(svc.impact_service, 'build_map', lambda _req: (_ for _ in ()).throw(RuntimeError('boom')))
    r = svc.refresh(AtlasContextRefreshV2Request(project_path=str(tmp_path), include_plan_item_impact_map=True, plan_pool={'items': []}))
    assert r.status in {'missing', 'empty_plan_pool'}
    assert 'impact_map_build_failed_non_blocking' in (r.warnings + r.context_notes)
    assert r.metadata['advisory_only'] is True
    assert r.metadata['executed'] is False


def test_service_builds_impact_map_when_absent(tmp_path: Path, monkeypatch):
    svc = ProjectIntelligenceContextRefreshV2Adapter(tmp_path)
    built = AtlasPlanItemImpactMap(status='available', impacts=[{'item_id': 'i1', 'impacted_files': ['a.py'], 'related_tests': ['tests/test_a.py']}])
    monkeypatch.setattr(svc.impact_service, 'build_map', lambda _req: built)
    r = svc.refresh(AtlasContextRefreshV2Request(project_path=str(tmp_path), include_plan_item_impact_map=True, plan_pool={'items': [{'item_id': 'i1'}]}))
    assert 'a.py' in r.impacted_files
    assert 'tests/test_a.py' in r.related_tests


def test_provided_impact_map_takes_priority(tmp_path: Path, monkeypatch):
    svc = ProjectIntelligenceContextRefreshV2Adapter(tmp_path)
    monkeypatch.setattr(svc.impact_service, 'build_map', lambda _req: (_ for _ in ()).throw(AssertionError('must not call build_map')))
    impact = {'status': 'available', 'impacts': [{'item_id': 'i1', 'impacted_files': ['a.py'], 'related_tests': ['tests/test_a.py'], 'recommended_commands': ['pytest tests/test_a.py'], 'manual_verification_steps': ['check'], 'ci_selection_hints': [{'k': 'v'}], 'reasons': ['r'], 'confidence': 'high'}]}
    r = svc.refresh(AtlasContextRefreshV2Request(project_path=str(tmp_path), item_id='i1', impact_map=impact, include_plan_item_impact_map=True, plan_pool={'items': [{'item_id': 'i1'}]}))
    assert r.impacted_files == ['a.py']


def test_metadata_safety_flags(tmp_path: Path):
    r = ProjectIntelligenceContextRefreshV2Adapter(tmp_path).refresh(
        AtlasContextRefreshV2Request(project_path=str(tmp_path), plan_pool={'items': []})
    )
    m = r.metadata
    assert m['advisory_only'] is True and m['executed'] is False and m['shell_executed'] is False
    assert m['remote_git_executed'] is False and m['auto_verification_triggered'] is False
    assert m['auto_test_execution_triggered'] is False and m['no_auto_build'] is True
    assert m['no_execution'] is True and m['commands_are_suggestions_only'] is True and m['context_refresh_v2'] is True
