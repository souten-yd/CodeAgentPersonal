from pathlib import Path


def test_vue_13_packaging_integration_contract() -> None:
    server = Path('app/server.py').read_text(encoding='utf-8').lower()
    main = Path('main.py').read_text(encoding='utf-8').lower()
    manifest = Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8').lower()

    assert 'configure_atlas_next_preview_route' in main
    assert 'web/atlas-next/dist' in server
    assert 'web/atlas-next/src' not in server
    assert 'atlas next preview unavailable.' in server
    assert 'raw_source_serving_allowed' in server
    assert 'default_route' in server
    assert 'ui_html_fallback' in server
    assert 'root_fallback' in server

    assert 'npm install' not in server
    assert 'npm run build' not in server

    assert '"vue_next_source_dir": "web/atlas-next"' in manifest
    assert '"vue_next_dist_dir": "web/atlas-next/dist"' in manifest
    assert '"vue_next_route_packaging_raw_source_allowed": false' in manifest
