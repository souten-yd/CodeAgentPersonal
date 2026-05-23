from pathlib import Path

def test_default_route_diagnostics_contract() -> None:
    text = Path('main.py').read_text(encoding='utf-8')
    for marker in [
        '/api/atlas/vue-next-default/diagnostics',
        'vue_next_default_enabled',
        'default_uses_validated_dist',
        'fallback_to_legacy_ui_on_invalid_dist',
        'backend_authoritative',
        'runtime_level',
    ]:
        assert marker in text
