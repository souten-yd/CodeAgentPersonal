from pathlib import Path


def test_vue_no_execution_routes_or_dynamic_code():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    forbidden = [
        '/api/atlas/level1/execute', 'dry-run', 'approval', 'safe_apply',
        'subprocess', 'execute-all', 'auto-continue', 'new Function', 'eval('
    ]
    for token in forbidden:
        assert token not in text
