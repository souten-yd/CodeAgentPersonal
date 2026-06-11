from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request
from agent.project_intelligence.adapters.planner_packaging_v2 import ProjectIntelligencePlannerPackagingV2Adapter
import agent.project_intelligence.adapters.planner_packaging_v2 as adapter_mod


def test_adapter_impacted_files_related_tests_and_advisory_prompt(tmp_path):
    adapter = ProjectIntelligencePlannerPackagingV2Adapter(tmp_path)
    req = AtlasPlannerPackagingV2Request(
        project_path=str(tmp_path),
        plan_item_impact_map={
            "status": "available",
            "impacts": [
                {
                    "item_id": "i1",
                    "impacted_files": ["app/main.py"],
                    "related_tests": ["tests/test_main.py"],
                    "confidence": "high",
                }
            ],
        },
        context_refresh_v2={"status": "available", "related_tests": []},
    )

    result = adapter.build_package(req)

    assert "app/main.py" in result.impacted_files
    assert "tests/test_main.py" in result.related_tests
    assert "ADVISORY REPOSITORY CONTEXT" in result.planner_context_text
    assert "DO NOT EXECUTE" in result.planner_context_text
    assert "manual-only" in result.planner_context_text
    assert "app/main.py" in result.planner_context_text
    assert "tests/test_main.py" in result.planner_context_text


def test_adapter_safety_flags(tmp_path):
    result = ProjectIntelligencePlannerPackagingV2Adapter(tmp_path).build_package(
        AtlasPlannerPackagingV2Request(project_path=str(tmp_path))
    )
    metadata = result.metadata

    assert metadata["advisory_only"] is True
    assert metadata["executed"] is False
    assert metadata["shell_executed"] is False
    assert metadata["remote_git_executed"] is False
    assert metadata["auto_verification_triggered"] is False
    assert metadata["auto_test_execution_triggered"] is False
    assert metadata["no_auto_build"] is True
    assert metadata["no_execution"] is True
    assert metadata["commands_are_suggestions_only"] is True
    assert metadata["planner_packaging_v2"] is True


def test_adapter_builder_failures_non_blocking(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(adapter_mod.ProjectIntelligenceRepoContextPackager, "build_package", boom)
    monkeypatch.setattr(adapter_mod.AtlasPlanItemImpactMapService, "build_map", boom)
    monkeypatch.setattr(adapter_mod.AtlasContextRefreshV2Service, "refresh", boom)

    req = AtlasPlannerPackagingV2Request(
        project_path=str(tmp_path),
        include_repo_context=True,
        include_plan_item_impact_map=True,
        include_context_refresh_v2=True,
        plan_pool={"items": []},
    )
    result = ProjectIntelligencePlannerPackagingV2Adapter(tmp_path).build_package(req)

    assert result.status in {"partial", "missing"}
    assert "repo_context_unavailable" in result.warnings
    assert "plan_item_impact_map_unavailable" in result.warnings
    assert "context_refresh_v2_unavailable" in result.warnings
