from agent.atlas_verification_planning_service import AtlasVerificationPlanningService
from agent.atlas_verification_planning_schema import AtlasVerificationPlanningRequest


def test_missing_index_non_blocking(tmp_path):
    r = AtlasVerificationPlanningService(data_root=tmp_path).build_plan(AtlasVerificationPlanningRequest(project_path=str(tmp_path/'repo')))
    assert r.status in {'missing','partial'}


def test_flags_false(tmp_path):
    r = AtlasVerificationPlanningService(data_root=tmp_path).build_plan(AtlasVerificationPlanningRequest())
    assert r.metadata['executed'] is False and r.metadata['shell_executed'] is False
    assert r.metadata['remote_git_executed'] is False and r.metadata['no_auto_build'] is True


def test_commands_suggested_only(tmp_path):
    r = AtlasVerificationPlanningService(data_root=tmp_path).build_plan(AtlasVerificationPlanningRequest())
    assert len(r.recommended_commands) <= 5
    assert len(r.manual_verification_steps) <= 5
