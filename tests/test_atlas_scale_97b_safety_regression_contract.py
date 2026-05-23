from pathlib import Path


def test_scale_97b_readiness_get_only_and_no_mutation_methods() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/level1/readiness', { method: 'GET' })" in text
    assert '/api/atlas/level1/readiness' in text
    for method in ["method: 'POST'", "method: 'PUT'", "method: 'PATCH'", "method: 'DELETE'"]:
        assert f"/api/atlas/level1/readiness', {{ {method}" not in text


def test_scale_97b_readiness_ui_and_endpoint_safety_markers() -> None:
    panel = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    for banned in ['<button', '@click', '<form', 'submit']:
        assert banned not in panel

    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    for banned_endpoint in [
        '/api/atlas/level1/execute',
        '/api/atlas/level1/dry-run',
        '/api/atlas/level1/apply',
        '/api/atlas/level1/approve',
        '/api/atlas/level1/rollback',
        '/api/atlas/level1/retry',
        '/api/atlas/level1/continue',
    ]:
        assert banned_endpoint not in client


def test_scale_97b_runtime_and_authority_policy_is_preserved() -> None:
    docs = '\n'.join([
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8'),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8'),
        Path('docs/atlas_autonomous_execution_readiness_policy.md').read_text(encoding='utf-8'),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8'),
    ])
    assert 'Runtime remains level_0_manual_only' in docs or 'runtime remains level_0_manual_only' in docs
    assert 'Level-1 execution remains disabled' in docs
    assert 'Autonomous execution remains disabled' in docs or 'autonomous execution remain disabled' in docs
    assert 'Vue execution capability remains none' in docs
    assert 'Backend workflow_state remains authoritative' in docs
