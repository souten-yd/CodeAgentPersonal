from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService


def test_fallback_continue_when_safe_apply_and_verification_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = AtlasLLMEvaluatorService()
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id='p1', trigger='manual', safe_apply_result={'status':'applied','actual_file_changed':True}, verification_result={'status':'passed'}))
    assert r.decision.decision == 'continue'
    assert r.decision.should_continue_autopilot is False


def test_fallback_stop_when_verification_failed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = AtlasLLMEvaluatorService()
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id='p1', trigger='manual', verification_result={'status':'failed'}))
    assert r.decision.decision == 'stop'
    assert r.decision.should_run_debug_review is True
    assert r.decision.should_restore is False
