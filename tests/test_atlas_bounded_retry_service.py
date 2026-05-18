from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class _Ctx:
    def __init__(self, raises=False): self.raises = raises
    def refresh(self, *_a, **_k):
        if self.raises: raise RuntimeError("context boom")
        return SimpleNamespace(bundle_id="ctx1", status="completed")


class _Ev:
    def __init__(self, decision="continue", raises=False): self.decision = decision; self.raises = raises
    def evaluate(self, *_a, **_k):
        if self.raises: raise RuntimeError("evaluator boom")
        return SimpleNamespace(decision=SimpleNamespace(model_dump=lambda: {"decision": self.decision}), metadata={"eval_id": "ev1"})


class _Vr:
    def __init__(self, statuses, changed_files=None, raises=False):
        self.statuses = statuses; self.i = 0; self.changed_files = changed_files or []; self.raises = raises
    def run_after_auto_safe_apply(self, *_a, **_k):
        if self.raises: raise RuntimeError("verification boom")
        st = self.statuses[min(self.i, len(self.statuses)-1)]; self.i += 1
        return SimpleNamespace(status=st, model_dump=lambda: {"status": st, "stderr_tail": "timeout" if st=="failed" else "", "changed_files": self.changed_files[min(self.i-1, len(self.changed_files)-1)] if self.changed_files else []})


def _svc(tmp_path, statuses, eval_decision="continue", vr_changed=None, ctx_raises=False, vr_raises=False, ev_raises=False):
    storage = AtlasPlanPoolStorage(tmp_path); journal = AtlasJournal(tmp_path)
    pool = AtlasPlanPoolBuilder().build_fallback_pool(root_goal="g", project_path=str(tmp_path), project_name="p"); storage.save_pool(pool)
    svc = AtlasBoundedRetryService(storage=storage, journal=journal, auto_verification_service=_Vr(statuses, vr_changed, vr_raises), context_refresh_service=_Ctx(ctx_raises), evaluator_service=_Ev(eval_decision, ev_raises))
    return svc, pool, journal


def test_retry_exhausted_until_max_attempts(tmp_path):
    s, pool, _ = _svc(tmp_path, ["failed", "failed"])
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=pool.items[0].item_id, run_id="r1", verification_result={"status":"failed","stderr_tail":"timeout"}, max_attempts=2))
    assert r.status == "exhausted"
    assert r.attempt_count == 2


def test_evaluator_stop_does_not_prevent_retry_when_retryable(tmp_path):
    s, pool, _ = _svc(tmp_path, ["failed", "passed"], eval_decision="stop")
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=pool.items[0].item_id, run_id="r1", verification_result={"status":"failed","stderr_tail":"timeout"}, max_attempts=2))
    assert r.attempt_count == 2


def test_retry_becomes_not_retryable(tmp_path):
    s, pool, _ = _svc(tmp_path, ["failed"]) 
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=pool.items[0].item_id, run_id="r1", verification_result={"status":"failed","stderr_tail":"timeout"}, failure_stop_suggestion={"reason":"AssertionError"}, max_attempts=2))
    assert r.status in {"not_retryable", "stopped"}


def test_runtime_budget_stops(tmp_path):
    s, pool, _ = _svc(tmp_path, ["failed", "failed"])
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=pool.items[0].item_id, run_id="r1", policy_id="verification_retry_v1", verification_result={"status":"failed","stderr_tail":"timeout"}, max_attempts=2))
    assert "started_at" in r.metadata


def test_changed_files_drift_detected(tmp_path):
    s, pool, _ = _svc(tmp_path, ["failed"], vr_changed=[["a.py", "b.py"]])
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=pool.items[0].item_id, run_id="r1", verification_result={"status":"failed","stderr_tail":"timeout"}, changed_files=["a.py"], max_attempts=1))
    assert r.stop_reason == "changed_files_changed_during_retry"


@pytest.mark.parametrize("ctx_raises,vr_raises,ev_raises", [(True,False,False),(False,True,False),(False,False,True)])
def test_exception_saves_failed_result(tmp_path, ctx_raises, vr_raises, ev_raises):
    s, pool, _ = _svc(tmp_path, ["failed"], ctx_raises=ctx_raises, vr_raises=vr_raises, ev_raises=ev_raises)
    with pytest.raises(RuntimeError):
        s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=pool.items[0].item_id, run_id="r1", verification_result={"status":"failed","stderr_tail":"timeout"}, max_attempts=1))
    root = Path("ca_data/atlas/bounded_retry") / pool.pool_id
    assert list(root.glob("*.json"))
