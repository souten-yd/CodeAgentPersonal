from types import SimpleNamespace

import agent.atlas_multi_item_autopilot_service as svc_mod
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _build(tmp_path, enforcement):
    pool = AtlasPlanPool(
        pool_id="p1", root_goal="g", project_path=str(tmp_path),
        metadata={"automation_features": {"quality_gate_enforcement": enforcement}},
        items=[AtlasPlanItem(
            item_id="i1", pool_id="p1", title="t", goal="g", item_type="implementation",
            risk_level="medium", status="ready", target_files=["a.txt"],
            metadata={"action_type": "create", "approval": {"decision": "approved"}, "proposed_content": "a\n"},
        )],
    )

    class Storage:
        def load_pool(self, pool_id): return pool
        def save_pool(self, p): pass

    class Journal:
        def append_event(self, *a, **k): pass

    class AutoSafe:
        def execute_one(self, request):
            return SimpleNamespace(status="applied", changed_files=["a.txt"],
                                   model_dump=lambda: {"status": "applied", "changed_files": ["a.txt"], "actual_file_changed": True, "file_results": [{"path": "a.txt", "status": "applied"}]})

    class Verification:
        def run_after_auto_safe_apply(self, request):
            return SimpleNamespace(status="skipped", warnings=["verification_command_missing"],
                                   model_dump=lambda: {"status": "skipped", "warnings": ["verification_command_missing"]})

    return AtlasMultiItemAutopilotService(
        storage=Storage(), journal=Journal(), automation_gate=AtlasAutomationGateService(),
        auto_safe_apply_service=AutoSafe(), auto_verification_service=Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda r: SimpleNamespace(status="available", bundle_id="c")),
        evaluator_service=SimpleNamespace(evaluate=lambda r: SimpleNamespace(metadata={"eval_id": "e"}, decision=SimpleNamespace(model_dump=lambda: {"decision": "continue"}))),
    )


def _req(tmp_path):
    return AtlasMultiItemAutopilotRequest(
        pool_id="p1", project_path=str(tmp_path), policy_id="full_auto_multi_item_v1",
        require_approval=False, include_context_refresh=False, include_evaluator=False,
    )


def _degraded_rollup(*a, **k):
    return {"degraded": True, "degrade_reasons": ["integration_failed"], "requirement_coverage": {}}


def test_block_enforcement_elevates_degraded_run_to_needs_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(svc_mod, "compute_run_quality_rollup", _degraded_rollup)
    out = _build(tmp_path, "block").run(_req(tmp_path))
    assert out.status == "needs_revision"
    assert out.stop_reason == "integration_failed"


def test_warn_enforcement_keeps_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(svc_mod, "compute_run_quality_rollup", _degraded_rollup)
    out = _build(tmp_path, "warn").run(_req(tmp_path))
    assert out.status == "partial"
