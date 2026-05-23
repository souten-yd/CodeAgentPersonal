from pathlib import Path

def test_route_selection_guard_summary_and_no_redirect_note() -> None:
    text = Path('web/atlas-next/src/components/DefaultReadinessPreflight.vue').read_text(encoding='utf-8')
    assert 'Route selection guard scope: read_only_default_readiness_metadata.' in text
    assert 'does not redirect to <code>/atlas-next</code>' in text

def test_server_routes_not_redirected_to_atlas_next() -> None:
    server = Path('app/server.py').read_text(encoding='utf-8')
    main = Path('main.py').read_text(encoding='utf-8')
    assert 'RedirectResponse' not in server or '/atlas-next' not in server
    assert 'RedirectResponse("/ui/")' in main
