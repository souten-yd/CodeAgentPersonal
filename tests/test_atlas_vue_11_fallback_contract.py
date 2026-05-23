from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server import configure_atlas_next_preview_route


def test_preview_route_not_default_and_ui_html_default_remains() -> None:
    text = Path('main.py').read_text(encoding='utf-8').lower()
    assert 'configure_atlas_next_preview_route(app)' in text
    manifest = Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8').lower()
    assert '"vue_next_default_enabled": true' in manifest
    assert Path('ui.html').is_file()


def test_missing_dist_invalid_dist_and_missing_index_fail_closed(tmp_path: Path) -> None:
    app_missing = FastAPI()
    configure_atlas_next_preview_route(app_missing, dist_dir=tmp_path / 'no_dist')
    client_missing = TestClient(app_missing)
    assert client_missing.get('/atlas-next').status_code == 404

    invalid = tmp_path / 'dist_invalid'
    invalid.mkdir()
    (invalid / 'index.html').write_text('<html><body>no atlas refs</body></html>', encoding='utf-8')
    app_invalid = FastAPI()
    configure_atlas_next_preview_route(app_invalid, dist_dir=invalid)
    c2 = TestClient(app_invalid)
    assert c2.get('/atlas-next').status_code == 404

    missing_index = tmp_path / 'dist_missing_index'
    missing_index.mkdir()
    app_missing_index = FastAPI()
    configure_atlas_next_preview_route(app_missing_index, dist_dir=missing_index)
    c3 = TestClient(app_missing_index)
    assert c3.get('/atlas-next').status_code == 404


def test_missing_asset_and_path_traversal_and_raw_source_safe_404(tmp_path: Path) -> None:
    dist = tmp_path / 'dist'
    assets = dist / 'assets'
    assets.mkdir(parents=True)
    (dist / 'index.html').write_text('<script src="/atlas-next/assets/app.js"></script>', encoding='utf-8')
    (assets / 'app.js').write_text('console.log(1)', encoding='utf-8')

    app = FastAPI()
    configure_atlas_next_preview_route(app, dist_dir=dist)
    client = TestClient(app)

    assert client.get('/atlas-next/assets/missing.js').status_code == 404
    assert client.get('/atlas-next/../../main.py').status_code == 404
    assert client.get('/atlas-next/src/main.ts').status_code == 404
    assert client.get('/atlas-next/route/without/ext').status_code == 200
