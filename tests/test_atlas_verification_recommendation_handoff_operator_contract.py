from pathlib import Path


def test_operator_contract_semantics_unchanged_manual_confirmation_still_present():
    text = Path('web/js/atlas_dashboard.js').read_text()
    assert 'EXECUTE ONE ACTION' in text
    assert 'verification_recommendation_handoff' in Path('app/api/atlas_pipeline.py').read_text()
