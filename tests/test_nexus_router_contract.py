from fastapi.testclient import TestClient

import main
from app.server import create_app


def _route(path: str, method: str, app=main.app):
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1
    return routes[0]


def test_create_app_nexus_read_only_fallback_endpoints_return_200():
    client = TestClient(create_app())

    summary = client.get("/nexus/summary")
    documents = client.get("/nexus/documents?project=default&q=")
    active_jobs = client.get("/nexus/jobs/active?limit=20")
    web_status = client.get("/nexus/web/status")

    assert summary.status_code == 200
    assert documents.status_code == 200
    assert active_jobs.status_code == 200
    assert web_status.status_code == 200


def test_create_app_nexus_fallback_payload_shapes_are_lightweight():
    client = TestClient(create_app())

    assert set(client.get("/nexus/summary").json()) == {
        "documents",
        "chunks",
        "reports",
        "active_jobs",
        "limits",
    }
    assert client.get("/nexus/documents?project=default&q=").json() == {"documents": []}
    assert client.get("/nexus/jobs/active?limit=20").json() == {"jobs": []}

    web_status = client.get("/nexus/web/status").json()
    assert web_status["enable_web"] is False
    assert web_status["configured"] is False
    assert web_status["searxng_configured"] is False
    assert web_status["stub"] is True
    assert web_status["non_fatal"] is True
    assert web_status["provider_status_active"]["configured"] is False


def test_create_app_nexus_fallback_does_not_call_production_providers(monkeypatch):
    def fail_provider(*args, **kwargs):
        raise AssertionError("production provider was called")

    monkeypatch.setattr(main, "nexus_summary_payload", fail_provider)
    monkeypatch.setattr(main, "nexus_documents_payload", fail_provider)
    monkeypatch.setattr(main, "nexus_active_jobs_payload", fail_provider)
    monkeypatch.setattr(main, "nexus_web_status_payload", fail_provider)

    client = TestClient(create_app())
    assert client.get("/nexus/summary").status_code == 200
    assert client.get("/nexus/documents?project=default&q=").status_code == 200
    assert client.get("/nexus/jobs/active?limit=20").status_code == 200
    assert client.get("/nexus/web/status").status_code == 200


def test_main_app_registers_nexus_providers_as_callables():
    assert callable(main.app.state.nexus_summary_provider)
    assert callable(main.app.state.nexus_documents_provider)
    assert callable(main.app.state.nexus_active_jobs_provider)
    assert callable(main.app.state.nexus_web_status_provider)


def test_main_app_nexus_routes_are_owned_by_api_router():
    expected = [
        ("/nexus/summary", "GET", "get_nexus_summary_api"),
        ("/nexus/documents", "GET", "get_nexus_documents_api"),
        ("/nexus/jobs/active", "GET", "get_nexus_active_jobs_api"),
        ("/nexus/web/status", "GET", "get_nexus_web_status_api"),
    ]
    for path, method, handler_name in expected:
        route = _route(path, method)
        assert route.endpoint.__module__ == "app.api.nexus"
        assert route.endpoint.__name__ == handler_name


def test_main_app_provider_shapes_match_nexus_read_only_contract(monkeypatch):
    monkeypatch.setattr(
        main.app.state,
        "nexus_summary_provider",
        lambda project="default": {
            "documents": 1,
            "chunks": 2,
            "reports": 3,
            "active_jobs": 4,
            "limits": {
                "max_upload_mb": 10,
                "max_upload_bytes": 10485760,
                "max_download_mb": 11,
                "max_total_download_mb": 12,
                "max_downloads": 13,
                "download_timeout_sec": 14,
            },
        },
    )
    monkeypatch.setattr(
        main.app.state,
        "nexus_documents_provider",
        lambda project="default", q="", limit=100: {"documents": []},
    )
    monkeypatch.setattr(
        main.app.state,
        "nexus_active_jobs_provider",
        lambda limit=50: {"jobs": []},
    )
    monkeypatch.setattr(
        main.app.state,
        "nexus_web_status_provider",
        lambda: {
            "enable_web": False,
            "provider": "searxng",
            "fallback_providers": [],
            "free_only": True,
            "paid_providers_enabled": False,
            "brave_search_api_key_set": False,
            "searxng_url": "",
            "searxng_configured": False,
            "configured": False,
            "active_provider": "searxng",
            "provider_status": {},
            "provider_status_active": {},
            "message": "unavailable",
            "searxng_state": "unavailable",
            "searxng_state_message": "unavailable",
            "non_fatal": True,
            "stub": True,
            "provider_errors": {},
            "last_provider_errors": {},
            "last_selected_provider": None,
            "last_non_fatal": None,
            "last_message": "",
            "last_search_at": None,
            "runpod_searxng_autostart_status": "",
            "runpod_searxng_autostart_hint": "",
        },
    )

    client = TestClient(main.app)
    assert set(client.get("/nexus/summary").json()) == {
        "documents",
        "chunks",
        "reports",
        "active_jobs",
        "limits",
    }
    assert client.get("/nexus/documents?project=default&q=").json() == {"documents": []}
    assert client.get("/nexus/jobs/active?limit=20").json() == {"jobs": []}
    assert set(client.get("/nexus/web/status").json()) == {
        "enable_web",
        "provider",
        "fallback_providers",
        "free_only",
        "paid_providers_enabled",
        "brave_search_api_key_set",
        "searxng_url",
        "searxng_configured",
        "configured",
        "active_provider",
        "provider_status",
        "provider_status_active",
        "message",
        "searxng_state",
        "searxng_state_message",
        "non_fatal",
        "stub",
        "provider_errors",
        "last_provider_errors",
        "last_selected_provider",
        "last_non_fatal",
        "last_message",
        "last_search_at",
        "runpod_searxng_autostart_status",
        "runpod_searxng_autostart_hint",
    }
