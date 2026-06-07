"""Self-correction loop: regenerate a patch from a verification failure, re-apply, re-verify."""
from __future__ import annotations

import tempfile
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest
from agent.atlas_self_correction_service import AtlasSelfCorrectionService


def _setup(risk="low"):
    tmp = Path(tempfile.mkdtemp())
    ca = tmp / "ca"; ca.mkdir()
    storage = AtlasPlanPoolStorage(ca)
    journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(item_id="step_1", pool_id="p", title="Create hello.py", goal="hello",
                         item_type="implementation", status="ready", risk_level=risk,
                         target_files=["hello.py"], metadata={"action_type": "create"})
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(tmp / "ws"), items=[item])
    storage.save_pool(pool); journal.save_plan_pool(pool)
    return storage, journal


class _FakePatchService:
    """Regeneration that always yields applicable content (simulates a fixed patch)."""
    def __init__(self, has_content=True):
        self.has_content = has_content
        self.calls = []

    def propose_for_item(self, request):
        self.calls.append(request.item_id)
        has = self.has_content
        class _R:
            status = "proposed"
            metadata = {
                "patch_content_available": has,
                "patch_generation": {
                    "state": "succeeded" if has else "failed",
                    "outcome": "success" if has else "failure",
                    "patch_content_available": has,
                },
            }
        return _R()


class _FakeApply:
    def __init__(self, status="applied"):
        self.status = status
        self.changed_files = ["hello.py"]
        self.calls = 0

    def execute_one(self, request):
        self.calls += 1
        outer = self
        class _R:
            status = outer.status
            changed_files = outer.changed_files
        return _R()


class _FakeVerify:
    """Fails the first N re-verifications, then passes."""
    def __init__(self, fail_times=1):
        self.fail_times = fail_times
        self.calls = 0

    def run_after_auto_safe_apply(self, request):
        self.calls += 1
        status = "failed" if self.calls <= self.fail_times else "passed"
        outer_status = status
        class _R:
            status = outer_status
            warnings = []
            def model_dump(self):
                return {"status": outer_status, "stdout_tail": "", "stderr_tail": "boom", "exit_code": 1}
        return _R()


def _req():
    return AtlasSelfCorrectionRequest(pool_id="p", item_id="step_1", run_id="r1",
                                      verification_result={"status": "failed", "stderr_tail": "boom", "exit_code": 1},
                                      max_attempts=2)


def test_recovers_when_regenerated_patch_passes_on_second_verification():
    storage, journal = _setup()
    svc = AtlasSelfCorrectionService(storage=storage, journal=journal,
                                     patch_proposal_service=_FakePatchService(has_content=True),
                                     auto_safe_apply_service=_FakeApply("applied"),
                                     auto_verification_service=_FakeVerify(fail_times=1))
    out = svc.run(_req())
    assert out.status == "recovered"
    assert out.final_verification_status == "passed"
    assert out.changed_files == ["hello.py"]


def test_exhausts_when_verification_keeps_failing():
    storage, journal = _setup()
    svc = AtlasSelfCorrectionService(storage=storage, journal=journal,
                                     patch_proposal_service=_FakePatchService(has_content=True),
                                     auto_safe_apply_service=_FakeApply("applied"),
                                     auto_verification_service=_FakeVerify(fail_times=99))
    out = svc.run(_req())
    assert out.status == "exhausted"
    assert out.attempts == 2


def test_skips_high_risk_items_no_auto_reapply():
    storage, journal = _setup(risk="high")
    apply = _FakeApply("applied")
    svc = AtlasSelfCorrectionService(storage=storage, journal=journal,
                                     patch_proposal_service=_FakePatchService(has_content=True),
                                     auto_safe_apply_service=apply,
                                     auto_verification_service=_FakeVerify(fail_times=0))
    out = svc.run(_req())
    assert out.status == "skipped"
    assert "risk_level_not_auto_reapplyable" in out.reason
    assert apply.calls == 0  # never re-applied a high-risk item


def test_stops_when_regeneration_yields_no_content():
    storage, journal = _setup()
    svc = AtlasSelfCorrectionService(storage=storage, journal=journal,
                                     patch_proposal_service=_FakePatchService(has_content=False),
                                     auto_safe_apply_service=_FakeApply("applied"),
                                     auto_verification_service=_FakeVerify(fail_times=99))
    out = svc.run(_req())
    assert out.status == "exhausted"
    assert out.reason == "patch_regeneration_no_content"


def test_configurable_risk_levels_allow_high_when_widened():
    """A caller may widen risk_levels to repair higher-risk items."""
    storage, journal = _setup(risk="high")
    apply = _FakeApply("applied")
    svc = AtlasSelfCorrectionService(storage=storage, journal=journal,
                                     patch_proposal_service=_FakePatchService(has_content=True),
                                     auto_safe_apply_service=apply,
                                     auto_verification_service=_FakeVerify(fail_times=1))
    req = AtlasSelfCorrectionRequest(pool_id="p", item_id="step_1", run_id="r1",
                                     verification_result={"status": "failed"}, max_attempts=2,
                                     risk_levels=["low", "medium", "high"])
    out = svc.run(req)
    assert out.status == "recovered"
    assert apply.calls >= 1  # high-risk item was re-applied because the gate was widened


def test_default_risk_levels_still_skip_high():
    """With the default (low/medium) a high-risk item is still skipped — guard preserved."""
    storage, journal = _setup(risk="high")
    apply = _FakeApply("applied")
    svc = AtlasSelfCorrectionService(storage=storage, journal=journal,
                                     patch_proposal_service=_FakePatchService(has_content=True),
                                     auto_safe_apply_service=apply,
                                     auto_verification_service=_FakeVerify(fail_times=0))
    out = svc.run(_req())  # default risk_levels = ["low", "medium"]
    assert out.status == "skipped"
    assert "risk_level_not_auto_reapplyable" in out.reason
    assert apply.calls == 0
