"""8th: a single failed item no longer hard-stops the whole run (honors max_failures), dependents of a
failed item are skipped, and a run that completed some items but failed others reports 'partial'.
Plus the planner-prompt guidance that static/trivial deliverables get no separate pytest test."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest


def _item(item_id, *, depends_on=()):
    return SimpleNamespace(
        item_id=item_id, target_files=[f"{item_id}.py"], metadata={}, risk_level="low",
        depends_on=list(depends_on), item_type="implementation", status="ready",
        title=item_id, description="", goal="", done_definition=[],
    )


def _pool(items):
    def get_item(iid):
        return next((it for it in items if it.item_id == iid), None)
    return SimpleNamespace(pool_id="p1", project_path="proj", items=items, get_item=get_item)


class _Apply:
    def execute_one(self, req):
        return SimpleNamespace(status="applied", changed_files=[], model_dump=lambda: {"status": "applied", "changed_files": []})


class _Verify:
    def __init__(self, vmap):
        self.vmap = vmap
        self.seen = []

    def run_after_auto_safe_apply(self, req):
        self.seen.append(req.item_id)
        st = self.vmap.get(req.item_id, "passed")
        return SimpleNamespace(status=st, warnings=[], model_dump=lambda: {"status": st})


class _Svc(AtlasMultiItemAutopilotService):
    def _check_eligibility(self, request, policy, item, *, target_files, changed_total):
        return {"status": "eligible", "planned_steps": []}

    def save_result(self, result):
        pass

    def resolve_project_path(self, request, pool, item):
        return "proj"


def _run(items, vmap, *, max_failures=3):
    pool = _pool(items)
    verify = _Verify(vmap)
    svc = _Svc(
        storage=SimpleNamespace(load_pool=lambda pid: pool, save_pool=lambda p: None),
        journal=SimpleNamespace(append_event=lambda *a, **k: None),
        automation_gate=None,
        auto_safe_apply_service=_Apply(),
        auto_verification_service=verify,
        context_refresh_service=None,
        evaluator_service=None,
    )
    svc.supervised_status_service = SimpleNamespace(build_status=lambda req: SimpleNamespace(multi_status_run_id="m", next_item=None, counts={}, model_dump=lambda: {}))
    req = AtlasMultiItemAutopilotRequest(
        pool_id="p1", workspace_id="default", project_path="proj", max_failures=max_failures,
        include_context_refresh=False, include_evaluator=False, include_bounded_retry=False,
        include_self_correction=False, include_harness_provisioning=False, include_correction_routing=False,
        require_approval=False,
    )
    return svc.run(req), verify


def test_failure_does_not_hard_stop_and_run_is_partial():
    # item2 fails; item3 must still be processed (no hard stop), and the run is 'partial'.
    items = [_item("i1"), _item("i2"), _item("i3")]
    out, verify = _run(items, {"i2": "failed"})
    assert verify.seen == ["i1", "i2", "i3"]  # processing continued past the failure
    assert out.completed_count == 2 and out.failed_count == 1
    assert out.status == "partial"
    assert out.stop_reason == "verification_failed"


def test_dependent_of_failed_item_is_skipped():
    items = [_item("i1"), _item("i2", depends_on=["i1"])]
    out, verify = _run(items, {"i1": "failed"})
    assert verify.seen == ["i1"]  # i2 never ran — its dependency failed
    skipped = [r for r in out.item_results if r.item_id == "i2"]
    assert skipped and skipped[0].status == "skipped" and skipped[0].reason == "dependency_failed"


def test_max_failures_one_still_hard_stops():
    items = [_item("i1"), _item("i2")]
    out, verify = _run(items, {"i1": "failed"}, max_failures=1)
    assert verify.seen == ["i1"]  # stopped after the first failure
    assert out.status == "stopped" and out.stop_reason == "max_failures_reached"


def test_all_pass_is_completed():
    out, _ = _run([_item("i1"), _item("i2")], {})
    assert out.status == "completed" and out.completed_count == 2 and out.failed_count == 0


def test_prompt_does_not_test_static_deliverables():
    p = Path("agent/agent_prompts.py").read_text(encoding="utf-8")
    assert "Do NOT create a separate unit-test file for a trivial or static deliverable" in p
    assert "Only write an automated test for executable CODE" in p
