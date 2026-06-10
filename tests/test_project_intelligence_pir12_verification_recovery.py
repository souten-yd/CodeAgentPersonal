from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_verification_gate_schema import AtlasVerificationRequest
from agent.atlas_verification_gate_service import AtlasVerificationGateService
from agent.project_intelligence.adapters.atlas_verification import AtlasVerificationBridge
from agent.project_intelligence.checkpoint import CheckpointController
from agent.project_intelligence.production_factory import build_production_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_PHASES, RolloutConfig
from agent.project_intelligence.service_registry import close_project_intelligence_service, register_project_intelligence_service
from agent.test_command_runner_schema import AtlasTestCommandBatchResult, AtlasTestCommandResult
from app.server import create_app


class _PassingBatchRunner:
    def run_command(self, request):
        return AtlasTestCommandResult(
            command=request.command,
            status="passed",
            returncode=0,
            stdout="ok",
            metadata=dict(request.metadata),
        )

    def run_many(self, requests, stop_on_failure=False):
        results = [
            self.run_command(request)
            for request in requests
        ]
        return AtlasTestCommandBatchResult(results=results, passed_count=len(results))


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    return repo


def _pool(repo: Path) -> AtlasPlanPool:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Verify app",
        goal="Verify app.py",
        item_type="implementation",
        status="completed",
        target_files=["app.py"],
        metadata={
            "blueprint_revision_id": "bp-item",
            "safe_apply": {
                "status": "applied",
                "change_snapshot_id": "snap-1",
                "project_intelligence_apply": {
                    "status": "recorded",
                    "correlation_id": "apply-1",
                    "twin_revision_id": "tw-apply",
                },
            },
        },
    )
    return AtlasPlanPool(
        pool_id="pool_1",
        root_goal="PIR-12 verification",
        project_path=str(repo),
        project_name="KasaneCore",
        status="running",
        items=[item],
        metadata={
            "workspace_id": "default",
            "requirement_revision_id": "req-1",
            "blueprint_revision_id": "bp-pool",
            "actual_twin_revision_id": "tw-pool",
            "source_revision_id": "src-pool",
            "plan_revision_id": "plan-rev-1",
        },
    )


def _store_pool(tmp_path: Path, pool: AtlasPlanPool) -> tuple[AtlasPlanPoolStorage, AtlasJournal]:
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return storage, journal


def test_manual_verification_records_project_intelligence_checkpoint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder = build_production_project_intelligence(
        ca_data_dir=tmp_path / "ca",
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "verification"}),
    )
    bridge = AtlasVerificationBridge(CheckpointController(tmp_path / "ca" / "project_intelligence" / "checkpoint.sqlite3"))
    try:
        service = AtlasVerificationGateService(
            journal=journal,
            storage=storage,
            test_runner=_PassingBatchRunner(),
            project_intelligence=service_holder.coordinator,
            verification_bridge=bridge,
        )

        result = service.verify_item(
            AtlasVerificationRequest(
                pool_id="pool_1",
                item_id="item_1",
                run_id="verify-1",
                metadata={"source_revision": "src-verify"},
            )
        )

        assert result.status == "passed"
        pi = result.metadata["project_intelligence_verification"]
        assert pi["status"] == "recorded"
        assert pi["accepted"] is True
        assert pi["checkpoint_id"].startswith("ckpt:")
        assert pi["convergence_report_id"]
        assert pi["decision_route"]["existing_services"] == ["continuation"]
        assert pi["revisions"]["source_revision"] == "src-verify"
        assert pi["revisions"]["actual_twin_revision_id"] == "tw-apply"
        saved = storage.load_pool("pool_1").get_item("item_1")
        assert saved.metadata["verification"]["project_intelligence_verification"]["checkpoint_id"] == pi["checkpoint_id"]
    finally:
        service_holder.close()


def test_manual_verification_replay_is_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder = build_production_project_intelligence(
        ca_data_dir=tmp_path / "ca",
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "verification"}),
    )
    bridge = AtlasVerificationBridge(CheckpointController(tmp_path / "ca" / "project_intelligence" / "checkpoint.sqlite3"))
    try:
        service = AtlasVerificationGateService(
            journal=journal,
            storage=storage,
            test_runner=_PassingBatchRunner(),
            project_intelligence=service_holder.coordinator,
            verification_bridge=bridge,
        )
        request = AtlasVerificationRequest(pool_id="pool_1", item_id="item_1", run_id="verify-1")

        first = service.verify_item(request)
        replay = service.verify_item(request)

        assert first.metadata["project_intelligence_verification"]["checkpoint_id"] == replay.metadata["project_intelligence_verification"]["checkpoint_id"]
        assert replay.metadata["project_intelligence_verification"]["idempotent_replay"] is True
    finally:
        service_holder.close()


def test_verification_api_sync_uses_registered_project_intelligence(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.state.atlas_test_command_runner = _PassingBatchRunner()
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    pool = _pool(repo)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    register_project_intelligence_service(
        app,
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "verification"}),
    )
    try:
        response = TestClient(app).post(
            "/api/atlas/verification/run?sync=1",
            json={
                "pool_id": "pool_1",
                "item_id": "item_1",
                "run_id": "verify-api",
                "metadata": {"source_revision": "src-api"},
            },
        )
    finally:
        close_project_intelligence_service(app)
        app.state.atlas_test_command_runner = None

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "passed"
    pi = body["metadata"]["project_intelligence_verification"]
    assert pi["status"] == "recorded"
    assert pi["revisions"]["source_revision"] == "src-api"
    assert pi["checkpoint_id"].startswith("ckpt:")


def test_auto_verification_records_project_intelligence_after_canonical_persistence(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder = build_production_project_intelligence(
        ca_data_dir=tmp_path / "ca",
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "verification"}),
    )
    bridge = AtlasVerificationBridge(CheckpointController(tmp_path / "ca" / "project_intelligence" / "checkpoint.sqlite3"))
    try:
        service = AtlasAutoVerificationService(
            journal=journal,
            storage=storage,
            command_runner=_PassingBatchRunner(),
            project_intelligence=service_holder.coordinator,
            verification_bridge=bridge,
        )

        result = service.run_after_auto_safe_apply(
            AtlasAutoVerificationRequest(
                pool_id="pool_1",
                item_id="item_1",
                run_id="verify-auto",
                command_id="node_check_dashboard",
                metadata={"source_revision": "src-auto"},
            )
        )

        assert result.status == "passed"
        pi = result.metadata["project_intelligence_verification"]
        assert pi["status"] == "recorded"
        assert pi["source"] == "auto"
        assert pi["checkpoint_id"].startswith("ckpt:")
        saved = storage.load_pool("pool_1").get_item("item_1")
        assert saved.metadata["auto_verification"]["project_intelligence_verification"]["source"] == "auto"
    finally:
        service_holder.close()
