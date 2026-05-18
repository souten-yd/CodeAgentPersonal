from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _mk_pool(journal, pool_id="p1"):
    item = AtlasPlanItem(item_id="i1", pool_id=pool_id, title="t", goal="g", metadata={"auto_safe_apply": {"status": "applied", "actual_file_changed": True}, "auto_verification": {"status": "passed"}, "failure_stop_suggestion": {"should_stop": False}, "target_files": ["a.py"]})
    pool = AtlasPlanPool(pool_id=pool_id, root_goal="g", items=[item])
    journal.save_plan_pool(pool)


def test_input_packet_resolves_from_item_auto_safe_apply_and_auto_verification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    j = AtlasJournal(tmp_path / "ca_data")
    _mk_pool(j)
    svc = AtlasLLMEvaluatorService(journal=j)
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", item_id="i1", trigger="manual"))
    assert r.input_packet.safe_apply_result["status"] == "applied"
    assert r.input_packet.verification_result["status"] == "passed"


def test_request_values_take_precedence_over_item_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    j = AtlasJournal(tmp_path / "ca_data")
    _mk_pool(j)
    svc = AtlasLLMEvaluatorService(journal=j)
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", item_id="i1", trigger="manual", safe_apply_result={"status": "blocked"}))
    assert r.input_packet.safe_apply_result["status"] == "blocked"


def test_service_save_result_rejects_pool_id_path_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = AtlasLLMEvaluatorService()
    try:
        svc.evaluate(AtlasEvaluatorRequest(pool_id="../x", trigger="manual"))
        assert False
    except ValueError:
        assert True


def test_diff_summary_extracted_from_context_bundle_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Path("ca_data/atlas/context_bundles/p1"); p.mkdir(parents=True)
    p.joinpath("ctx_1.json").write_text('{"bundle_id":"ctx_1","sources":[{"source_type":"git_diff","summary":"A"}]}', encoding="utf-8")
    svc = AtlasLLMEvaluatorService()
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", trigger="manual"))
    assert r.input_packet.diff_summary == "A"


def test_prompt_contains_non_negotiable_rules():
    svc = AtlasLLMEvaluatorService()
    req = AtlasEvaluatorRequest(pool_id="p1", trigger="manual")
    packet, _, _ = svc.build_input_packet(req, type("P", (), {"policy_id": "guarded_evaluator_v1", "max_diff_chars": 100})(), [])
    prompt, _ = svc.build_prompt(packet, type("P", (), {})(), 2000)
    assert "Non-negotiable rules" in prompt and "Untrusted Context" in prompt


def test_llm_invalid_json_sets_parse_failed_metadata(tmp_path, monkeypatch):
    class Bad:
        def evaluate(self, *_):
            return "not-json"

    monkeypatch.chdir(tmp_path)
    svc = AtlasLLMEvaluatorService(llm_client=Bad())
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", trigger="manual"))
    assert r.metadata["llm_parse_failed"] is True
    assert "llm_json_parse_failed" in r.warnings


def test_continue_blocked_when_verification_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = AtlasLLMEvaluatorService()
    r = svc.evaluate(AtlasEvaluatorRequest(pool_id="p1", trigger="manual", safe_apply_result={"status": "applied", "actual_file_changed": True}))
    assert r.decision.decision != "continue"
