from pathlib import Path


def test_root_route_guarded_default_logic_present() -> None:
    text = Path('main.py').read_text(encoding='utf-8')
    for marker in [
        'def can_serve_atlas_next_default()',
        'validate_atlas_next_dist()',
        'ATLAS_NEXT_DEFAULT_ENABLED',
        'def root()',
        'serve_existing_ui_index()',
    ]:
        assert marker in text
