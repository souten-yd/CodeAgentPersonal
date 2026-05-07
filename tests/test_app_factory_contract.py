from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server import create_app
import main


def test_create_app_skeleton_is_available_for_future_factory_migration():
    app = create_app()

    assert isinstance(app, FastAPI)


def test_create_app_can_optionally_serve_static_assets(tmp_path):
    css_dir = tmp_path / "css"
    css_dir.mkdir()
    (css_dir / "app.css").write_text(":root{--bg:#000;}\n", encoding="utf-8")
    app = create_app(web_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/static/css/app.css")

    assert response.status_code == 200
    assert "css" in response.headers.get("content-type", "").lower()
    assert ":root" in response.text


def test_main_app_contract_remains_fastapi_app():
    assert hasattr(main, "app")
    assert isinstance(main.app, FastAPI)


def test_main_health_endpoint_still_returns_ok():
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_main_static_css_asset_still_serves_successfully():
    client = TestClient(main.app)

    response = client.get("/static/css/app.css")

    assert response.status_code == 200
    assert "css" in response.headers.get("content-type", "").lower()


def test_main_static_js_asset_still_serves_successfully():
    client = TestClient(main.app)

    response = client.get("/static/js/app.js")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type or "text/plain" in content_type
