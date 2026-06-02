import tempfile
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest
from agent.atlas_self_correction_service import AtlasSelfCorrectionService


def _setup(*, risk: str = "high", target_files: list[str] | None = None, requires_user_confirmation: bool = False, metadata: dict | None = None):
    tmp = Path(tempfile.mkdtemp())
    ca = tmp / "ca"
    ca.mkdir()
    storage = AtlasPlanPoolStorage(ca)
    journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(
        item_id="step_1",
        pool_id="p",
        title="Repair visual artifact",
        goal="Repair visual animation",
        item_type="implementation",
        status="ready",
        risk_level=risk,
        requires_user_confirmation=requires_user_confirmation,
        target_files=target_files or ["index.html"],
        metadata={"action_type": "create"},
    )
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(tmp / "ws"), items=[item], metadata=metadata or {})
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return storage, journal


class _FakePatchService:
    def __init__(self):
        self.calls = 0

    def propose_for_item(self, request):
        self.calls += 1

        class _R:
            status = "proposed"
            metadata = {"patch_content_available": True}

        return _R()


class _FakeApply:
    def __init__(self):
        self.calls = 0
        self.changed_files = ["index.html"]

    def execute_one(self, request):
        self.calls += 1
        outer = self

        class _R:
            status = "applied"
            changed_files = outer.changed_files

        return _R()


class _FakeVerify:
    def run_after_auto_safe_apply(self, request):
        class _R:
            status = "passed"
            warnings = []

            def model_dump(self):
                return {"status": "passed", "warnings": []}

        return _R()


def _service(storage, journal, apply):
    return AtlasSelfCorrectionService(
        storage=storage,
        journal=journal,
        patch_proposal_service=_FakePatchService(),
        auto_safe_apply_service=apply,
        auto_verification_service=_FakeVerify(),
    )


def _req():
    return AtlasSelfCorrectionRequest(
        pool_id="p",
        item_id="step_1",
        run_id="r1",
        verification_result={"status": "failed", "warnings": ["visual_contract_failed"]},
        max_attempts=1,
    )


def test_high_risk_frontend_artifact_uses_audited_exception():
    storage, journal = _setup(risk="high", target_files=["index.html"])
    apply = _FakeApply()

    out = _service(storage, journal, apply).run(_req())

    assert out.status == "recovered"
    assert out.metadata["high_risk_frontend_exception"] is True
    assert out.metadata["exception_scope"] == "frontend_only_artifact"
    assert apply.calls == 1


def test_high_risk_execution_file_still_skips():
    storage, journal = _setup(risk="high", target_files=["deploy.py"])
    apply = _FakeApply()

    out = _service(storage, journal, apply).run(_req())

    assert out.status == "skipped"
    assert out.reason == "risk_level_not_auto_reapplyable:high"
    assert apply.calls == 0


def test_critical_frontend_artifact_still_skips():
    storage, journal = _setup(risk="critical", target_files=["index.html"])
    apply = _FakeApply()

    out = _service(storage, journal, apply).run(_req())

    assert out.status == "skipped"
    assert out.reason == "risk_level_not_auto_reapplyable:critical"
    assert apply.calls == 0


def test_high_risk_frontend_confirmation_requires_envelope_bounds():
    storage, journal = _setup(risk="high", target_files=["index.html"], requires_user_confirmation=True)
    apply = _FakeApply()

    out = _service(storage, journal, apply).run(_req())

    assert out.status == "skipped"
    assert out.reason == "high_risk_frontend_exception_requires_active_envelope"
    assert apply.calls == 0


def test_high_risk_frontend_confirmation_runs_inside_high_envelope():
    envelope = {
        "status": "active",
        "bounds": {
            "max_risk_level": "high",
            "allowed_paths": ["index.html", "styles/"],
        },
    }
    storage, journal = _setup(
        risk="high",
        target_files=["index.html"],
        requires_user_confirmation=True,
        metadata={"envelope": envelope},
    )
    apply = _FakeApply()

    out = _service(storage, journal, apply).run(_req())

    assert out.status == "recovered"
    assert out.metadata["high_risk_frontend_exception"] is True
    assert apply.calls == 1
