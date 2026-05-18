from pathlib import Path

import pytest

from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _mk_pool(journal, pool_id="p1"):
    item = AtlasPlanItem(item_id="i1", pool_id=pool_id, title="t", goal="g", metadata={"auto_safe_apply": {"status": "applied", "actual_file_changed": True}, "auto_verification": {"status": "passed"}, "failure_stop_suggestion": {"should_stop": False}, "target_files": ["a.py"]})
    pool = AtlasPlanPool(pool_id=pool_id, root_goal="g", items=[item])
    journal.save_plan_pool(pool)


def _events(j, pool_id, run_id):
    p = j.pipeline_run_dir(pool_id, run_id) / "events.ndjson"
    if not p.exists():
        return []
    return [e for e in p.read_text(encoding="utf-8").splitlines() if e]


def test_evaluator_saves_json_and_markdown_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = AtlasLLMEvaluatorService()
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", trigger="manual"))
    root = Path("ca_data/atlas/evaluator_results/p1")
    assert root.joinpath(f"{r.metadata['eval_id']}.json").exists()
    md = root.joinpath(f"{r.metadata['eval_id']}.md")
    assert md.exists()
    body = md.read_text(encoding="utf-8")
    assert "decision" in body and "confidence" in body and "Recommended Next Actions" in body
    assert "raw_llm_output" not in body


def test_evaluator_event_suite_recorded(tmp_path, monkeypatch):
    class Bad:
        def evaluate(self, *_):
            return "not-json"

    monkeypatch.chdir(tmp_path)
    j = AtlasJournal(tmp_path / "ca_data")
    _mk_pool(j)
    svc = AtlasLLMEvaluatorService(journal=j, llm_client=Bad())
    svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", item_id="i1", run_id="r1", trigger="manual"))
    raw = "\n".join(_events(j, "p1", "r1"))
    assert "evaluator_started" in raw
    assert "evaluator_completed" in raw
    assert "evaluator_fallback_used" in raw


def test_evaluator_policy_override_blocked_and_failed_events(tmp_path, monkeypatch):
    class ForceContinue:
        def evaluate(self, *_):
            return '{"decision":"continue","confidence":0.9,"reasons":[],"risks":[],"recommended_next_actions":[],"requires_manual_review":false,"should_run_debug_review":false,"should_generate_patch_proposal":false,"should_restore":false,"should_continue_autopilot":true,"summary":"x"}'

    monkeypatch.chdir(tmp_path)
    j = AtlasJournal(tmp_path / "ca_data")
    svc = AtlasLLMEvaluatorService(journal=j, llm_client=ForceContinue())
    svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", run_id="r2", trigger="manual", verification_result={"status": "failed"}, safe_apply_result={"status": "applied", "actual_file_changed": True}))
    raw = "\n".join(_events(j, "p1", "r2"))
    assert "evaluator_policy_override" in raw

    from agent import atlas_llm_evaluator_service as mod
    policy = mod.get_evaluator_policy("guarded_evaluator_v1")
    policy.require_context_bundle = True
    monkeypatch.setattr(mod, "get_evaluator_policy", lambda _pid: policy)
    svc.evaluate(AtlasEvaluatorRequest(pool_id="p2", run_id="r3", trigger="manual"))
    raw3 = "\n".join(_events(j, "p2", "r3"))
    assert "evaluator_blocked" in raw3

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    svc2 = AtlasLLMEvaluatorService(journal=j)
    monkeypatch.setattr(svc2, "build_input_packet", boom)
    with pytest.raises(RuntimeError):
        svc2.evaluate(AtlasEvaluatorRequest(pool_id="p9", run_id="r9", trigger="manual"))
    raw9 = "\n".join(_events(j, "p9", "r9"))
    assert "evaluator_failed" in raw9
