from pathlib import Path

def test_component_exists_and_display_only_contract() -> None:
    text = Path('web/atlas-next/src/components/ApprovalDryRunPreview.vue').read_text(encoding='utf-8').lower()
    assert 'approval & dry-run readiness preview' in text
    assert 'actions unavailable in vue18' in text
    for banned in ['<button', '@click', 'submit', 'fetch(', 'atlasclient']:
        assert banned not in text
    for marker in ['approval-required count', 'dry-run ready', 'dry-run blocked reason', 'missing readiness gates', 'readiness warnings', 'backend-owned metadata note']:
        assert marker in text
