from fastapi.testclient import TestClient
import main


def test_can_serve_atlas_next_default_true_when_dist_is_valid(monkeypatch) -> None:
    # POST-SCALE-160-UI-DEFAULT-RECONFIRM flipped ATLAS_NEXT_DEFAULT_ENABLED
    # to False. The guarded selector itself is unchanged: when the env enables
    # the Atlas Next default AND the dist is valid, it still chooses atlas-next.
    monkeypatch.setattr(main, 'ATLAS_NEXT_DEFAULT_ENABLED', True)
    monkeypatch.setattr(main, 'validate_atlas_next_dist', lambda: {'dist_exists': True, 'index_present': True, 'valid': True})
    monkeypatch.setattr(main.os.path, 'exists', lambda _p: True)
    monkeypatch.setattr(main.os.path, 'isdir', lambda _p: True)

    allowed, diag = main.can_serve_atlas_next_default()
    assert allowed is True
    assert diag['default_route_selected'] == 'atlas-next'


def test_can_serve_atlas_next_default_false_when_env_flag_disabled(monkeypatch) -> None:
    monkeypatch.setattr(main, 'ATLAS_NEXT_DEFAULT_ENABLED', False)
    monkeypatch.setattr(main, 'validate_atlas_next_dist', lambda: {'dist_exists': True, 'index_present': True, 'valid': True})
    monkeypatch.setattr(main.os.path, 'exists', lambda _p: True)
    monkeypatch.setattr(main.os.path, 'isdir', lambda _p: True)

    allowed, diag = main.can_serve_atlas_next_default()
    assert allowed is False
    assert diag['default_route_selected'] == 'legacy-ui'


def test_root_route_falls_back_to_legacy_when_dist_is_invalid(monkeypatch) -> None:
    monkeypatch.setattr(main, 'validate_atlas_next_dist', lambda: {'dist_exists': True, 'index_present': True, 'valid': False})
    monkeypatch.setattr(main, 'serve_existing_ui_index', lambda: 'legacy-ui')
    client = TestClient(main.app)

    response = client.get('/')
    assert response.status_code == 200
    assert response.json() == 'legacy-ui'
