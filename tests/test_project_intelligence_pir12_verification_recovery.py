from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_continuation_service import AtlasContinuationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_recovery_service import AtlasRecoveryService
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


class _FailingBatchRunner(_PassingBatchRunner):
    def run_command(self, request):
        return AtlasTestCommandResult(
            command=request.command,
            status="failed",
            returncode=1,
            stderr="AssertionError: failed",
            metadata=dict(request.metadata),
        )

    def run_many(self, requests, stop_on_failure=False):
        results = [self.run_command(request) for request in requests]
        return AtlasTestCommandBatchResult(results=results, failed_count=len(results))


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


def _verification_service(tmp_path: Path, storage, journal, runner):
    service_holder = build_production_project_intelligence(
        ca_data_dir=tmp_path / "ca",
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "verification"}),
    )
    bridge = AtlasVerificationBridge(CheckpointController(tmp_path / "ca" / "project_intelligence" / "checkpoint.sqlite3"))
    service = AtlasVerificationGateService(
        journal=journal,
        storage=storage,
        test_runner=runner,
        project_intelligence=service_holder.coordinator,
        verification_bridge=bridge,
    )
    return service_holder, service


def _record_manual_verification(tmp_path: Path, storage, journal, runner=None, run_id: str = "verify-1"):
    service_holder, service = _verification_service(tmp_path, storage, journal, runner or _PassingBatchRunner())
    result = service.verify_item(
        AtlasVerificationRequest(
            pool_id="pool_1",
            item_id="item_1",
            run_id=run_id,
            metadata={"source_revision": f"src-{run_id}"},
        )
    )
    return service_holder, result


def test_manual_verification_records_project_intelligence_checkpoint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder, service = _verification_service(tmp_path, storage, journal, _PassingBatchRunner())
    try:
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
    service_holder, service = _verification_service(tmp_path, storage, journal, _PassingBatchRunner())
    try:
        request = AtlasVerificationRequest(pool_id="pool_1", item_id="item_1", run_id="verify-1")

        first = service.verify_item(request)
        replay = service.verify_item(request)

        assert first.metadata["project_intelligence_verification"]["checkpoint_id"] == replay.metadata["project_intelligence_verification"]["checkpoint_id"]
        assert replay.metadata["project_intelligence_verification"]["idempotent_replay"] is True
    finally:
        service_holder.close()


def test_recovery_and_continuation_resume_from_project_intelligence_checkpoint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder, _ = _record_manual_verification(tmp_path, storage, journal, run_id="verify-resume")
    try:
        recovery = AtlasRecoveryService(journal).recover_pool("pool_1")
        checkpoint = recovery.metadata["project_intelligence_checkpoint"]
        assert checkpoint["resume_action"] == "resume"
        assert checkpoint["blind_resume_allowed"] is True
        assert recovery.next_action == "Resume from the Project Intelligence checkpoint without duplicate apply or verification."

        continuation = AtlasContinuationService(journal).build_pool_summary("pool_1")
        assert continuation.metadata["project_intelligence_resume_action"] == "resume"
        assert continuation.metadata["project_intelligence_blind_resume_allowed"] is True
        assert "project_intelligence_resume_action: resume" in continuation.continuation_prompt
    finally:
        service_holder.close()


def test_recovery_api_prevents_blind_resume_after_external_edit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder, _ = _record_manual_verification(tmp_path, storage, journal, run_id="verify-external")
    service_holder.close()
    (repo / "app.py").write_text("print('external change')\n", encoding="utf-8")

    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    response = TestClient(app).get("/api/atlas/recovery/pools/pool_1")

    assert response.status_code == 200, response.text
    recovery = response.json()["recovery_summary"]
    checkpoint = recovery["metadata"]["project_intelligence_checkpoint"]
    assert recovery["status"] == "stale"
    assert checkpoint["resume_action"] == "refresh_needed"
    assert checkpoint["blind_resume_allowed"] is False
    assert "project_intelligence_external_source_change" in recovery["warnings"]


def test_failed_verification_routes_to_bounded_repair_before_continuation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder, result = _record_manual_verification(
        tmp_path,
        storage,
        journal,
        runner=_FailingBatchRunner(),
        run_id="verify-failed",
    )
    try:
        assert result.status == "failed"
        recovery = AtlasRecoveryService(journal).recover_pool("pool_1")
        checkpoint = recovery.metadata["project_intelligence_checkpoint"]
        assert checkpoint["resume_action"] == "repair_current_item"
        assert "bounded_retry" in checkpoint["decision_route"]["existing_services"]
        assert recovery.next_action == "Run bounded repair/retry for the current item before downstream continuation."
    finally:
        service_holder.close()


def test_recovery_maps_critical_and_unsafe_project_intelligence_decisions(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder, _ = _record_manual_verification(tmp_path, storage, journal, run_id="verify-critical")
    service_holder.close()

    pool = storage.load_pool("pool_1")
    item = pool.get_item("item_1")
    pi = item.metadata["verification"]["project_intelligence_verification"]
    pi["decision_route"] = {"action": "request_critical_decision", "existing_services": ["critical_decision"]}
    item.metadata["verification"]["project_intelligence_verification"] = pi
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    critical = AtlasRecoveryService(journal).recover_pool("pool_1")
    assert critical.status == "blocked"
    assert critical.metadata["project_intelligence_checkpoint"]["resume_action"] == "request_critical_decision"
    assert "critical decision" in critical.next_action.lower()

    pool = storage.load_pool("pool_1")
    item = pool.get_item("item_1")
    pi = item.metadata["verification"]["project_intelligence_verification"]
    pi["decision_route"] = {"action": "halt_unsafe", "existing_services": ["failure_stop", "continuation"]}
    item.metadata["verification"]["project_intelligence_verification"] = pi
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    unsafe = AtlasRecoveryService(journal).recover_pool("pool_1")
    assert unsafe.status == "blocked"
    assert unsafe.metadata["project_intelligence_checkpoint"]["resume_action"] == "halt_unsafe"
    assert "halt without mutation" in unsafe.next_action.lower()


def test_completed_pool_requires_canonical_verification_and_project_intelligence_gate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    storage, journal = _store_pool(tmp_path, _pool(repo))
    service_holder, _ = _record_manual_verification(
        tmp_path,
        storage,
        journal,
        runner=_FailingBatchRunner(),
        run_id="verify-final-gate",
    )
    service_holder.close()
    pool = storage.load_pool("pool_1")
    pool.status = "completed"
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    recovery = AtlasRecoveryService(journal).recover_pool("pool_1")
    gate = recovery.metadata["project_intelligence_final_gate"]
    assert recovery.status == "blocked"
    assert gate["passed"] is False
    assert any("canonical_verification_not_passed" in reason for reason in gate["blocked_reasons"])
    assert "project_intelligence_final_gate_blocked" in recovery.warnings


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
