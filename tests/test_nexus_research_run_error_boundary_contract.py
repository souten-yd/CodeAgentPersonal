from fastapi.testclient import TestClient

from app.server import create_app


def test_nexus_research_run_provider_attribute_error_returns_structured_error():
    app = create_app()

    def broken_provider(_payload):
        raise AttributeError("missing source_profile")

    app.state.nexus_recursive_research_provider = broken_provider
    client = TestClient(app)

    response = client.post(
        "/nexus/research/run",
        json={"query": "latest news", "recursive_search": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "error"
    assert payload["error"] == "nexus_research_run_failed"
    assert payload["provider"] == "nexus_recursive_research_provider"
    assert "missing source_profile" in payload["message"]
    assert payload["request"]["query"] == "latest news"
    assert payload["request"]["source_profile"] == "web"
    assert payload["request"]["news_budget"] is None
