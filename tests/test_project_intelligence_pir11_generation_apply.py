"""PIR-11 Proposal and Safe Apply Project Intelligence integration tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.production_factory import build_production_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, RolloutConfig


class _ApplyAdapter:
    implementation_executor = object()

    def __init__(self, result: dict) -> None:
        self.result = result

    def evaluate_safe_apply(self, item, pool, **kwargs):
        return SimpleNamespace(decision="allow")

    def apply_low_risk_item(self, item, pool, request):
        return self.result


def _pool(tmp_path: Path, *, metadata: dict | None = None) -> AtlasPlanPool:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Update app",
        goal="Update app",
        description="Update app.py",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["app.py"],
        metadata={
            "action_type": "update",
            "approval": {"decision": "approved"},
            "proposed_content": "print('new')\n",
        },
    )
    return AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Ship PIR-11",
        project_path=str(tmp_path),
        project_name="KasaneCore",
        items=[item],
        metadata=metadata or {},
    )


def _store_pool(tmp_path: Path, pool: AtlasPlanPool) -> tuple[AtlasPlanPoolStorage, AtlasJournal]:
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return storage, journal


def test_patch_proposal_persists_generation_context_metadata(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "app.py").write_text("print('old')\n", encoding="utf-8")
    storage, journal = _store_pool(tmp_path, _pool(project, metadata={"actual_twin_revision_id": "tw-base"}))
    coordinator = build_project_intelligence(rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}))

    service = AtlasPatchProposalService(
        journal=journal,
        storage=storage,
        llm_json_fn=None,
        project_intelligence=coordinator,
    )
    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="gen_1", source_type="plan_item")
    )

    assert result.status in {"failed", "proposed"}
    item = storage.load_pool("pool_1").get_item("item_1")
    metadata = item.metadata["patch_proposal"]["metadata"]["project_intelligence_generation"]
    assert metadata["mode"] == "active"
    assert metadata["used_intelligence"] is True
    assert metadata["context_manifest_id"] == "active:generation"
    assert metadata["base_revision"] == "tw-base"


def test_stale_generation_context_blocks_before_llm_call(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "app.py").write_text("print('old')\n", encoding="utf-8")
    storage, journal = _store_pool(tmp_path, _pool(project))
    coordinator = build_project_intelligence(rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}))
    calls = {"count": 0}

    def llm(_prompt, _schema):
        calls["count"] += 1
        return {"proposed_content": "print('new')\n"}

    service = AtlasPatchProposalService(
        journal=journal,
        storage=storage,
        llm_json_fn=llm,
        project_intelligence=coordinator,
    )
    result = service.propose_for_item(
        AtlasPatchProposalRequest(
            pool_id="pool_1",
            item_id="item_1",
            run_id="gen_stale",
            source_type="plan_item",
            metadata={"base_revision": "tw-old", "current_actual_revision": "tw-new"},
        )
    )

    assert result.status == "blocked"
    assert calls["count"] == 0
    assert "project_intelligence_generation_blocked" in result.warnings
    assert result.metadata["project_intelligence_generation"]["blocking_reason"] == "stale_actual_revision"


def test_safe_apply_records_project_intelligence_after_canonical_apply(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "app.py").write_text("print('new')\n", encoding="utf-8")
    service_holder = build_production_project_intelligence(
        ca_data_dir=tmp_path / "ca",
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}),
    )
    try:
        storage, journal = _store_pool(tmp_path, _pool(project, metadata={"actual_twin_revision_id": "tw-base", "blueprint_revision_id": "bp-base"}))
        service = AtlasSafeApplyExecutionService(
            journal=journal,
            storage=storage,
            safe_apply_adapter=_ApplyAdapter(
                {"status": "applied", "actual_file_changed": True, "changed_files": ["app.py"], "file_results": [{"path": "app.py", "status": "applied"}]}
            ),
            workspace_root=project,
            project_intelligence=service_holder.coordinator,
        )

        result = service.execute_item(
            AtlasSafeApplyExecutionRequest(
                pool_id="pool_1",
                item_id="item_1",
                run_id="apply_1",
                metadata={"base_revision": "tw-base", "new_source_revision": "src-new"},
            )
        )

        assert result.status == "applied"
        pi_apply = result.metadata["project_intelligence_apply"]
        assert pi_apply["status"] == "recorded"
        assert pi_apply["accepted"] is True
        assert pi_apply["refresh_requested"] is True
        assert pi_apply["twin_revision_id"]
        assert pi_apply["convergence_report_id"]
        assert pi_apply["convergence_decision"]["action"] == "continue"
        item = storage.load_pool("pool_1").get_item("item_1")
        assert item.metadata["safe_apply"]["project_intelligence_apply"]["correlation_id"] == "apply_1"
    finally:
        service_holder.close()


def test_safe_apply_project_intelligence_notification_is_idempotent(tmp_path) -> None:
    calls = {"count": 0}

    class _Rollout:
        def mode_for_phase(self, _phase):
            return "active"

    class _Coordinator:
        rollout = _Rollout()

        def record_apply_result(self, request):
            calls["count"] += 1
            return SimpleNamespace(accepted=True, refresh_requested=True, twin_revision_id="tw-child", diagnostics=[])

    project = tmp_path / "repo"
    project.mkdir()
    storage, journal = _store_pool(tmp_path, _pool(project))
    item = storage.load_pool("pool_1").get_item("item_1")
    item.metadata.setdefault("safe_apply", {})["project_intelligence_apply"] = {"status": "recorded", "correlation_id": "apply_1"}
    pool = storage.load_pool("pool_1")
    pool.items[0] = item
    storage.save_pool(pool)
    service = AtlasSafeApplyExecutionService(
        journal=journal,
        storage=storage,
        safe_apply_adapter=_ApplyAdapter(
            {"status": "applied", "actual_file_changed": True, "changed_files": ["app.py"], "file_results": [{"path": "app.py", "status": "applied"}]}
        ),
        workspace_root=project,
        project_intelligence=_Coordinator(),
    )

    result = service.execute_item(AtlasSafeApplyExecutionRequest(pool_id="pool_1", item_id="item_1", run_id="apply_1"))

    assert result.status == "applied"
    assert calls["count"] == 0
    assert result.metadata["project_intelligence_apply"]["idempotent_replay"] is True
