from pathlib import Path


def test_route_selection_guard_summary_and_no_redirect_note() -> None:
    text = Path('web/atlas-next/src/components/DefaultReadinessPreflight.vue').read_text(encoding='utf-8')
    assert 'Route selection guard scope: guarded_default_apply_metadata.' in text
    assert 'Root route serves Atlas Next only after valid dist verification.' in text
    assert 'Root route fails closed to legacy UI when the dist is missing or invalid.' in text
    assert '<code>/ui.html</code> remains unchanged and does not redirect to <code>/atlas-next</code>.' in text


def test_main_routes_preserve_legacy_fallback_and_no_atlas_next_redirect() -> None:
    main_text = Path('main.py').read_text(encoding='utf-8')
    assert '@app.get("/")' in main_text
    assert 'atlas_next_allowed, _ = can_serve_atlas_next_default()' in main_text
    assert 'return serve_existing_ui_index()' in main_text
    assert '@app.get("/ui")' in main_text
    assert 'return RedirectResponse("/ui/")' in main_text
    assert 'RedirectResponse("/atlas-next")' not in main_text
    assert "RedirectResponse('/atlas-next')" not in main_text


def test_server_module_has_no_root_or_ui_html_redirect_to_atlas_next() -> None:
    server_text = Path('app/server.py').read_text(encoding='utf-8')
    assert 'RedirectResponse("/atlas-next")' not in server_text
    assert "RedirectResponse('/atlas-next')" not in server_text
    assert '@app.get("/atlas-next")' in server_text
    assert 'Atlas Next preview unavailable.' in server_text
    assert 'preview_health_state' in server_text
