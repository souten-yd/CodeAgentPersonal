from fastapi.testclient import TestClient

from app.api.system_status import (
    default_health_payload,
    default_system_summary_payload,
    default_system_usage_payload,
)
from app.server import create_app
import main


def test_create_app_system_status_endpoints_return_fallback_payloads():
    client = TestClient(create_app())

    health = client.get("/health")
    summary = client.get("/system/summary")
    usage = client.get("/system/usage")

    assert health.status_code == 200
    assert health.json() == default_health_payload()
    assert summary.status_code == 200
    assert summary.json() == default_system_summary_payload()
    assert usage.status_code == 200
    assert usage.json() == default_system_usage_payload()


def test_create_app_system_status_fallbacks_do_not_require_runtime_probe_providers():
    app = create_app()
    client = TestClient(app)

    assert not hasattr(app.state, "health_provider")
    assert not hasattr(app.state, "system_summary_provider")
    assert not hasattr(app.state, "system_usage_provider")

    assert client.get("/health").json() == {
        "ok": True,
        "status": "ok",
    }
    assert client.get("/system/summary").json() == {
        "ok": True,
        "runtime": "factory",
        "summary": {},
        "note": "system summary provider unavailable",
    }
    assert client.get("/system/usage").json() == {
        "ok": True,
        "usage": {},
        "note": "system usage provider unavailable",
    }


def test_main_app_system_status_routes_use_provider_backed_existing_shapes(monkeypatch):
    monkeypatch.setattr(main, "health_payload", lambda: {"status": "ok"})
    monkeypatch.setattr(
        main.app.state,
        "health_provider",
        main.health_payload,
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "system_summary_provider",
        lambda: {
            "health": {"llm": "unreachable", "sandbox": "docker unavailable"},
            "model": {
                "status": "idle",
                "current_key": "test-key",
                "current_name": "Test Model",
                "vram_gb": 0,
                "eta_sec": 0,
            },
            "usage": {
                "cpu_percent": 1.0,
                "ram_used_mb": 2,
                "ram_total_mb": 3,
                "gpu_backend": "none",
                "vram_confidence": "unknown",
                "vram_source_backend": "none",
                "gpus": [],
                "updated_at": "test",
            },
        },
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "system_usage_provider",
        lambda: {
            "cpu_percent": 1.0,
            "ram_total_mb": 3,
            "ram_used_mb": 2,
            "gpu_backend": "none",
            "gpu_backend_selected": "auto",
            "gpus": [],
            "updated_at": "test",
        },
        raising=False,
    )
    client = TestClient(main.app)

    assert client.get("/health").json() == {"status": "ok"}

    summary = client.get("/system/summary").json()
    assert set(summary) == {"health", "model", "usage"}
    assert set(summary["model"]) == {
        "status",
        "current_key",
        "current_name",
        "vram_gb",
        "eta_sec",
    }
    assert set(summary["usage"]) == {
        "cpu_percent",
        "ram_used_mb",
        "ram_total_mb",
        "gpu_backend",
        "vram_confidence",
        "vram_source_backend",
        "gpus",
        "updated_at",
    }

    usage = client.get("/system/usage").json()
    assert set(usage) == {
        "cpu_percent",
        "ram_total_mb",
        "ram_used_mb",
        "gpu_backend",
        "gpu_backend_selected",
        "gpus",
        "updated_at",
    }
