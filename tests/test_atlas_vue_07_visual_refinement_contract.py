from pathlib import Path


def test_vue_07_visual_refinement_contract() -> None:
    components = '\n'.join(
        p.read_text(encoding='utf-8').lower()
        for p in Path('web/atlas-next/src/components').glob('*.vue')
    )

    for required in [
        'read-only',
        'metadata-only',
        'level 0 manual-only',
        'backend workflow state remains authoritative',
        'existing ui.html remains default',
        'static mount deferred',
        'disabled/read-only',
    ]:
        assert required in components

    assert ('<button disabled' in components) or ('aria-disabled="true"' in components)

    for forbidden in [
        '@click', 'executeaction', 'approveaction', 'applypatch', 'rollbackaction',
        'restoreaction', 'verifyaction', 'retryaction', 'continueaction',
        'safe_apply', 'execute-all', 'auto-continue',
    ]:
        assert forbidden not in components
