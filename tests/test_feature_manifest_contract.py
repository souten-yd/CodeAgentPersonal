import json
from pathlib import Path

from tests.helpers.ui_contract import load_root_ui_html_text

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "web" / "feature_manifest.json"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def assert_selector_exists_in_html(selector, html):
    if selector.startswith("#"):
        dom_id = selector[1:]
        assert f'id="{dom_id}"' in html or f"id='{dom_id}'" in html
    elif selector.startswith("["):
        token = selector.strip("[]").split("=")[0]
        assert token in html
    else:
        assert selector in html


def test_feature_manifest_is_valid_json():
    data = load_manifest()
    assert data["version"] == 1
    assert data["app"] == "KasaneCore"


def test_feature_manifest_has_required_top_level_keys():
    data = load_manifest()
    for key in ["tabs", "root_panels", "required_controls", "storage_keys", "modules"]:
        assert key in data
        assert isinstance(data[key], list)


def test_feature_manifest_selectors_exist_in_ui_html():
    data = load_manifest()
    html = load_root_ui_html_text()
    for section in ["tabs", "root_panels", "required_controls"]:
        for item in data[section]:
            selector = item.get("selector")
            assert selector, item
            assert_selector_exists_in_html(selector, html)


def test_feature_manifest_modules_are_loaded_by_ui_html():
    data = load_manifest()
    html = load_root_ui_html_text()
    for module in data["modules"]:
        path = module["path"]
        assert f'<script src="{path}"></script>' in html


def test_feature_manifest_storage_keys_are_known_in_code():
    data = load_manifest()
    html = load_root_ui_html_text()
    js_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "web" / "js").glob("*.js")
    )
    combined = html + "\n" + js_text
    for item in data["storage_keys"]:
        assert item["key"] in combined


def test_feature_manifest_includes_runtime_diagnostics_button():
    data = load_manifest()
    controls = data["required_controls"]
    assert any(c.get("selector") == "#runtime-diagnostics-copy-btn" for c in controls)
