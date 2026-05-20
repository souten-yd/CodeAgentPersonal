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


def test_commands_from_related_tests_and_limits(tmp_path, monkeypatch):
    svc = AtlasVerificationPlanningService(data_root=tmp_path)
    related = [f"tests/test_{i}.py" for i in range(20)] + [f"src/a{i}.spec.ts" for i in range(4)] + [f"tests/test_{i}.py" for i in range(20, 40)]

    class FakePkg:
        status = "available"
        related_tests = related
        impacted_files = ["a.py"]
        warnings = []
        confidence = "high"

    monkeypatch.setattr(svc.packager, "build_package", lambda _req: FakePkg())
    r = svc.build_plan(AtlasVerificationPlanningRequest(project_path=str(tmp_path / "repo")))
    assert any(cmd.startswith("pytest ") for cmd in r.recommended_commands)
    assert any(cmd.startswith("npm test -- ") for cmd in r.recommended_commands)
    assert len(r.related_tests) <= 30
    assert len(r.recommended_commands) <= 5
    assert all(len(h.related_tests) <= 10 for h in r.per_item_hints)


def test_metadata_safety_flags(tmp_path):
    r = AtlasVerificationPlanningService(data_root=tmp_path).build_plan(AtlasVerificationPlanningRequest())
    assert r.metadata["advisory_only"] is True
    assert r.metadata["commands_are_suggestions_only"] is True
    assert r.metadata["executed"] is False
    assert r.metadata["shell_executed"] is False
    assert r.metadata["remote_git_executed"] is False
    assert r.metadata["auto_verification_triggered"] is False
    assert r.metadata["auto_test_execution_triggered"] is False
    assert r.metadata["no_auto_build"] is True
    assert r.metadata["no_execution"] is True
