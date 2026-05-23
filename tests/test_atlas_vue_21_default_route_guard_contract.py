from pathlib import Path
from fastapi.testclient import TestClient
import main


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


def test_can_serve_atlas_next_default_true_when_dist_is_valid(monkeypatch) -> None:
    monkeypatch.setattr(main, 'validate_atlas_next_dist', lambda: {'dist_exists': True, 'index_present': True, 'valid': True})
    monkeypatch.setattr(main.os.path, 'exists', lambda _p: True)
    monkeypatch.setattr(main.os.path, 'isdir', lambda _p: True)
    allowed, diag = main.can_serve_atlas_next_default()
    assert allowed is True
    assert diag['default_route_selected'] == 'atlas-next'


def test_root_route_falls_back_to_legacy_when_dist_is_invalid(monkeypatch) -> None:
    monkeypatch.setattr(main, 'validate_atlas_next_dist', lambda: {'dist_exists': True, 'index_present': True, 'valid': False})
    monkeypatch.setattr(main, 'serve_existing_ui_index', lambda: 'legacy-fallback')
    monkeypatch.setattr(main, 'UI_DIR', '/tmp')
    client = TestClient(main.app)
    res = client.get('/')
    assert res.status_code == 200
    assert res.json() == 'legacy-fallback'
