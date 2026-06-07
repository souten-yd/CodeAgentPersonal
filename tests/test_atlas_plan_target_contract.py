from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_plan_target_contract import (
    materialize_structural_targets,
    normalize_plan_for_review,
    normalize_plan_targets,
    validate_plan_target_contract,
)
from agent.plan_reviewer import PlanReviewer
from agent.plan_schema import ImplementationStep, Plan
from agent.requirement_schema import RequirementDefinition


def test_normalizer_is_idempotent_for_directory_targets() -> None:
    first = normalize_plan_targets(
        title="Set up project structure",
        description="Create directories for source code, assets, and tests.",
        action_type="create",
        target_files=["src", "assets", "tests"],
    )
    second = normalize_plan_targets(
        title="Set up project structure",
        description="Create directories for source code, assets, and tests.",
        action_type="create",
        patch_task_kind=first.patch_task_kind,
        target_files=first.target_files,
        target_directories=first.target_directories,
        operations=[op.model_dump() for op in first.operations],
        assumptions=first.assumptions,
    )

    assert first.patch_task_kind == "structural_change"
    assert first.target_files == []
    assert first.target_directories == ["src", "assets", "tests"]
    assert first.model_dump(exclude={"normalization_diagnostics"}) == second.model_dump(exclude={"normalization_diagnostics"})


def test_top_level_legacy_target_files_fallback_does_not_reinject_directories() -> None:
    plan = Plan(
        plan_id="plan_1",
        requirement_id="req_1",
        user_goal="Create project structure",
        requirement_summary="Create src and assets directories.",
        target_files=["src", "assets"],
        implementation_steps=[
            ImplementationStep(
                step_id="step_1",
                title="Create structure",
                description="Create directories for source and assets.",
                goal="Create repository structure.",
                action_type="create",
                acceptance_criteria=["Directories are represented in Git."],
            )
        ],
        test_plan=["inspect"],
        rollback_plan=["remove created files"],
    )

    normalized = normalize_plan_for_review(plan)

    assert normalized.target_files == []
    assert normalized.target_directories == ["src", "assets"]
    assert normalized.implementation_steps[0].target_files == []
    assert normalized.implementation_steps[0].target_directories == ["src", "assets"]


def test_extensionless_known_files_stay_files() -> None:
    normalized = normalize_plan_targets(
        title="Create files and directory",
        description="Create Dockerfile, Makefile, LICENSE and src directory.",
        action_type="create",
        target_files=["Dockerfile", "Makefile", "LICENSE", "src"],
    )

    assert normalized.target_files == ["Dockerfile", "Makefile", "LICENSE"]
    assert normalized.target_directories == ["src"]


def test_plan_reviewer_does_not_mutate_input_plan() -> None:
    plan = normalize_plan_for_review(
        Plan(
            plan_id="plan_1",
            requirement_id="req_1",
            user_goal="Create structure",
            requirement_summary="Create src directory.",
            implementation_steps=[
                ImplementationStep(
                    step_id="step_1",
                    title="Create src",
                    description="Create src directory.",
                    action_type="create",
                    target_directories=["src"],
                    acceptance_criteria=["src is materialized by tracked files."],
                )
            ],
            test_plan=["inspect"],
            rollback_plan=["remove created files"],
        )
    )
    before = plan.model_dump()
    req = RequirementDefinition(
        requirement_id="req_1",
        source_task_id="task_1",
        user_input="Create src directory.",
        interpreted_goal="Create src directory.",
        done_definition=["src exists"],
    )

    result = PlanReviewer().review(requirement=req, plan=plan, nexus_context={}, repository_context="")

    assert result.recommended_next_action in {"proceed", "ask_user"}
    assert plan.model_dump() == before


def test_materializer_does_not_mutate_item_or_backflow_gitkeep() -> None:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Create structure",
        goal="Create src directory.",
        patch_task_kind="structural_change",
        target_directories=["src"],
        operations=[{"type": "create_structure", "paths": ["src"]}],
    )
    before = item.model_dump()

    result = materialize_structural_targets(item)

    assert result.status == "materialized"
    assert result.patch_target_files == ["src/.gitkeep"]
    assert item.model_dump() == before
    assert item.target_files == []


def test_remove_directory_is_unsupported() -> None:
    result = validate_plan_target_contract(
        {
            "patch_task_kind": "structural_change",
            "target_directories": ["src"],
            "operations": [{"type": "remove_directory", "path": "src"}],
        }
    )

    assert result.ok is False
    assert "unsupported_operation:remove_directory" in result.reasons


def test_storage_load_only_fills_compatibility_defaults(tmp_path: Path) -> None:
    storage = AtlasPlanPoolStorage(tmp_path)
    path = storage.pool_path("pool_1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"pool_id":"pool_1","root_goal":"g","status":"ready","items":[{"item_id":"item_1","pool_id":"pool_1","title":"t","goal":"g","target_files":["src"]}]}',
        encoding="utf-8",
    )

    loaded = storage.load_pool("pool_1")

    assert loaded.status == "ready"
    assert loaded.items[0].target_files == ["src"]
    assert loaded.items[0].target_directories == []
    assert loaded.items[0].patch_task_kind == ""
    assert path.read_text(encoding="utf-8").count("target_directories") == 0


def test_structural_patch_materialization_semantic_validation_passes(tmp_path: Path) -> None:
    calls: list[str] = []

    def llm(_system: str, user: str) -> dict:
        calls.append(user)
        return {
            "target_files": ["src/.gitkeep"],
            "file_changes": [{"path": "src/.gitkeep", "action_type": "create", "proposed_content": "\n"}],
        }

    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Create src",
        goal="Create src directory.",
        description="Create src directory.",
        status="ready",
        risk_level="low",
        patch_task_kind="structural_change",
        target_directories=["src"],
        operations=[{"type": "create_structure", "paths": ["src"]}],
        metadata={"action_type": "create"},
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Create src", project_path=str(tmp_path), items=[item])
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    result = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm).propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is True
    assert result.proposal is not None
    assert result.proposal.target_files == ["src/.gitkeep"]
    assert result.proposal.metadata["semantic_validation"]["status"] == "passed"
    assert storage.load_pool("pool_1").get_item("item_1").target_files == []


def test_structural_retry_gets_structured_semantic_feedback(tmp_path: Path) -> None:
    calls: list[str] = []

    def llm(_system: str, user: str) -> dict:
        calls.append(user)
        if len(calls) == 1:
            return {"target_files": ["src"]}
        return {
            "target_files": ["src/.gitkeep"],
            "file_changes": [{"path": "src/.gitkeep", "action_type": "create", "proposed_content": "\n"}],
        }

    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Create src",
        goal="Create src directory.",
        description="Create src directory.",
        status="ready",
        risk_level="low",
        patch_task_kind="structural_change",
        target_directories=["src"],
        operations=[{"type": "create_structure", "paths": ["src"]}],
        metadata={"action_type": "create"},
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Create src", project_path=str(tmp_path), items=[item])
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    result = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm).propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is True
    assert len(calls) == 2
    assert "semantic_validation" in calls[1]
    assert "semantic_validation" in calls[1]


def test_unsafe_paths_block_before_llm(tmp_path: Path) -> None:
    called = False

    def llm(_system: str, _user: str) -> dict:
        nonlocal called
        called = True
        return {}

    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Unsafe",
        goal="Create unsafe path",
        status="ready",
        risk_level="low",
        patch_task_kind="structural_change",
        target_directories=["../src"],
        operations=[{"type": "create_structure", "paths": ["../src"]}],
        metadata={"action_type": "create"},
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Unsafe", project_path=str(tmp_path), items=[item])
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    result = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm).propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", source_type="plan_item", run_id="run_1")
    )

    assert result.status == "blocked"
    assert called is False
    assert any("unsafe" in warning for warning in result.warnings)
