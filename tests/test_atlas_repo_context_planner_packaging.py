from agent.atlas_repo_context_planner_packager import AtlasRepoContextPlannerPackager
from agent.atlas_repo_context_schema import AtlasRepoContextRequest


def test_packager_missing_index_is_non_blocking(tmp_path):
    req = AtlasRepoContextRequest(project_path=str(tmp_path / 'missing'))
    pkg = AtlasRepoContextPlannerPackager(data_root=tmp_path).build_package(req)
    assert pkg.status == 'missing'
    assert 'Advisory' in pkg.planner_context_text


def test_packager_limits_size(tmp_path):
    project = tmp_path / 'p'; project.mkdir()
    req = AtlasRepoContextRequest(project_path=str(project), changed_files=['a.py'])
    pkg = AtlasRepoContextPlannerPackager(data_root=tmp_path).build_package(req)
    assert len(pkg.impacted_files) <= 50
    assert len(pkg.related_tests) <= 30
    assert len(pkg.planner_context_text) <= 6000


def test_impacted_test_recommendation_is_suggestion_only(tmp_path):
    req = AtlasRepoContextRequest(project_path=str(tmp_path / 'p'))
    rec = AtlasRepoContextPlannerPackager(data_root=tmp_path).build_impacted_test_recommendation(req)
    assert rec.metadata['commands_are_suggestions_only'] is True
    assert rec.metadata['executed'] is False
    assert rec.metadata['shell_executed'] is False
