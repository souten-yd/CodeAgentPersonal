from pathlib import Path


def test_metadata_export_controls_present_and_non_execution_labeled():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert 'Copy readiness JSON' in text
    assert 'Download readiness JSON' in text
    assert 'Copy visible gate summary' in text
    forbidden = ['execute', 'apply', 'approve', 'verify', 'rollback', 'retry', 'continue', 'dry-run']
    for token in forbidden:
        assert token not in 'Copy readiness JSON Download readiness JSON Copy visible gate summary'.lower()
