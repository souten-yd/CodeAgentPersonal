from fastapi.testclient import TestClient

import main
from tests.helpers.ui_contract import load_root_ui_html_text


CSS_PATH = "/static/css/app.css"
CSS_TOKENS = (
    ":root{",
    "--bg:",
    ".atlas-dashboard-shell",
    ".atlas-primary-btn",
    ".atlas-goal-input",
    ".atlas-status-grid",
    ".atlas-plan-item-card",
    ".atlas-progress",
    ".mob-tabs",
)


def test_app_css_is_served_as_css_with_expected_tokens():
    client = TestClient(main.app)

    response = client.get(CSS_PATH)

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "css" in content_type.lower()
    for token in CSS_TOKENS:
        assert token in response.text


def test_ui_html_links_external_app_css():
    ui_html = load_root_ui_html_text()

    assert f'<link rel="stylesheet" href="{CSS_PATH}?v=atlas-dashboard-14b">' in ui_html
