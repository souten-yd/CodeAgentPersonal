from fastapi.testclient import TestClient

import main
from tests.helpers.ui_contract import load_root_ui_html_text


JS_PATH = "/static/js/app.js"
BOOTSTRAP_TOKEN = "KASANE_UI_BOOTSTRAP_LOADED"


def test_app_js_is_served_with_expected_bootstrap_token():
    client = TestClient(main.app)

    response = client.get(JS_PATH)

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type or "text/plain" in content_type
    assert BOOTSTRAP_TOKEN in response.text


def test_ui_html_loads_external_app_js():
    ui_html = load_root_ui_html_text()

    assert f'<script src="{JS_PATH}"></script>' in ui_html
