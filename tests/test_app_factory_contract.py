from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server import create_app
from app.services.system_usage import UsageCollectorPorts, UsageDiagnosticsPort
import main


def test_create_app_skeleton_is_available_for_future_factory_migration():
    app = create_app()

    assert isinstance(app, FastAPI)


def test_create_app_can_optionally_serve_static_assets(tmp_path):
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text(
        "<!doctype html><title>Test UI</title><main>ready</main>\n",
        encoding="utf-8",
    )
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "dummy.txt").write_text("asset ready\n", encoding="utf-8")
    web_dir = tmp_path / "web"
    css_dir = web_dir / "css"
    css_dir.mkdir(parents=True)
    (css_dir / "app.css").write_text(":root{--bg:#000;}\n", encoding="utf-8")
    app = create_app(ui_dir=ui_dir, assets_dir=assets_dir, web_dir=web_dir)
    client = TestClient(app)

    ui_response = client.get("/ui/")
    asset_response = client.get("/assets/dummy.txt")
    static_response = client.get("/static/css/app.css")

    assert ui_response.status_code == 200
    assert "text/html" in ui_response.headers.get("content-type", "").lower()
    assert "Test UI" in ui_response.text
    assert asset_response.status_code == 200
    assert asset_response.text == "asset ready\n"
    assert static_response.status_code == 200
    assert "css" in static_response.headers.get("content-type", "").lower()
    assert ":root" in static_response.text


def test_create_app_can_optionally_serve_workspace_index(tmp_path):
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>Workspace</title><main>workspace ready</main>\n",
        encoding="utf-8",
    )
    app = create_app(workspace_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/workspace/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "").lower()
    assert "workspace ready" in response.text


def test_main_app_system_usage_providers_are_callable():
    assert callable(main.app.state.health_provider)
    assert callable(main.app.state.system_usage_provider)
    assert callable(main.app.state.system_usage_debug_provider)


def test_main_app_system_summary_provider_is_callable():
    assert callable(main.app.state.system_summary_provider)


def test_main_app_system_usage_ports_are_registered():
    settings = main.app.state.system_usage_settings
    diagnostics = main.app.state.system_usage_diagnostics
    ports = main.app.state.system_usage_ports

    assert callable(settings.get_setting)
    assert callable(settings.set_setting)
    assert isinstance(diagnostics, UsageDiagnosticsPort)
    assert isinstance(ports, UsageCollectorPorts)
    assert ports.settings is settings
    assert ports.diagnostics is diagnostics


def test_main_system_usage_settings_port_delegates_to_main_settings_helpers(monkeypatch):
    calls = []

    def fake_settings_get(key: str) -> str | None:
        calls.append(("get", key))
        return "fake-value"

    def fake_settings_set(key: str, value: str) -> None:
        calls.append(("set", key, value))

    monkeypatch.setattr(main, "settings_get", fake_settings_get)
    monkeypatch.setattr(main, "settings_set", fake_settings_set)

    settings = main.app.state.system_usage_settings

    assert settings.get_setting("gpu_usage_backend") == "fake-value"
    settings.set_setting("gpu_usage_backend", "auto")
    assert calls == [
        ("get", "gpu_usage_backend"),
        ("set", "gpu_usage_backend", "auto"),
    ]


def test_main_usage_diagnostics_adapter_roundtrips_via_main_helpers():
    diagnostics = main.app.state.system_usage_diagnostics
    expected = {"probe": "test", "ok": True}

    diagnostics.set_last_usage_diag(expected)

    assert diagnostics.get_last_usage_diag() == expected
    assert main._get_last_usage_diag() == expected


def test_main_app_contract_remains_fastapi_app():
    assert hasattr(main, "app")
    assert isinstance(main.app, FastAPI)


def test_create_app_health_endpoint_returns_ok():
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "status": "ok"}


def test_create_app_system_readiness_endpoint_returns_ready():
    app = create_app()
    client = TestClient(app)

    response = client.get("/system/readiness")

    assert response.status_code == 200
    assert response.json()["fastapi"] == "ready"


def test_main_health_endpoint_still_returns_ok():
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_main_system_readiness_endpoint_still_returns_ready():
    client = TestClient(main.app)

    response = client.get("/system/readiness")

    assert response.status_code == 200
    assert response.json()["fastapi"] == "ready"


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


def test_main_ui_serves_index_when_available():
    index_path = main.Path(main.UI_DIR) / "index.html"
    if not index_path.is_file():
        return
    client = TestClient(main.app)

    response = client.get("/ui/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "").lower()


def test_main_system_usage_provider_delegates_to_service_collector(monkeypatch):
    calls = []
    expected = {"cpu_percent": 1, "gpus": [], "updated_at": "test"}

    def fake_collect_system_usage_info(*, ports, debug_mode=False):
        calls.append((ports, debug_mode))
        return expected

    monkeypatch.setattr(main, "collect_system_usage_info", fake_collect_system_usage_info)

    assert main.get_system_usage_info(debug_mode=True) is expected
    assert calls == [(main.app.state.system_usage_ports, True)]
