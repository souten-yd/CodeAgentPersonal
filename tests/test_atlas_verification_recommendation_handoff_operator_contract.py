from pathlib import Path


def test_operator_contract_runtime_sources_present():
    text = Path('agent/atlas_next_action_orchestrator_service.py').read_text(encoding='utf-8')
    assert '_resolve_verification_recommendation_handoff' in text
    assert 'pool.metadata' in text
    assert 'item.metadata' in text
    assert 'verification_recommendation_handoff_unavailable' in text
    assert 'commands_are_suggestions_only' in text


def test_operator_confirmation_requirements_unchanged():
    text = Path('agent/atlas_guarded_operator_loop_service.py').read_text(encoding='utf-8')
    assert "request.confirmation_text!='EXECUTE ONE ACTION'" in text
    assert 'require_dry_run_first' in text
