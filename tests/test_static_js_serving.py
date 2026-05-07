import pytest
from fastapi.testclient import TestClient

import main
from tests.helpers.ui_js_contract import (
    APP_JS_PATH,
    ECHO_JS_PATH,
    NEXUS_JS_PATH,
    PANELS_JS_PATH,
    SETTINGS_JS_PATH,
    SKILLS_MEMORY_JS_PATH,
)


BOOTSTRAP_TOKEN = "KASANE_UI_BOOTSTRAP_LOADED"


@pytest.mark.parametrize(
    ("js_path", "representative_token"),
    (
        (APP_JS_PATH, BOOTSTRAP_TOKEN),
        (SETTINGS_JS_PATH, "function openSettings"),
        (SKILLS_MEMORY_JS_PATH, "async function refreshSkills"),
        (PANELS_JS_PATH, "function switchTab"),
        (NEXUS_JS_PATH, "function renderNexusDocuments"),
        (ECHO_JS_PATH, "function _echoSetStatus"),
    ),
)
def test_static_js_asset_is_served_with_expected_content_type_and_token(
    js_path: str,
    representative_token: str,
):
    client = TestClient(main.app)

    response = client.get(js_path)

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type or "text/plain" in content_type
    assert representative_token in response.text
