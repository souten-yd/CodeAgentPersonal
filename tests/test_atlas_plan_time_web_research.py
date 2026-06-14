"""PIBIH-5: plan-time Nexus web-research decision + bounded execution."""

from __future__ import annotations

from agent.atlas_plan_time_research import AtlasPlanTimeResearchService, should_research

ENV = "ATLAS_NEXUS_WEB_RESEARCH"


class _FakeClient:
    """A fake Nexus web-research client recording calls."""

    def __init__(self, payload=None, raises=False) -> None:
        self.calls: list = []
        self._payload = payload or {
            "status": "completed",
            "summary": "Use libfoo v2 with the new auth flow.",
            "findings": [{"title": "libfoo docs", "content": "install libfoo and call connect()", "url": "http://x"}],
        }
        self._raises = raises

    def run_research(self, request):
        self.calls.append(request)
        if self._raises:
            raise RuntimeError("searxng unavailable")
        return self._payload


# --- eligibility decision -----------------------------------------------------

def test_should_research_eligible_on_external_signal():
    ok, reason = should_research("Add OAuth2 integration with the Stripe API")
    assert ok is True and reason.startswith("external_signal")


def test_should_research_ineligible_for_internal_refactor():
    ok, reason = should_research("Rename the helper function and update its callers")
    assert ok is False and reason == "no_external_signal"


def test_should_research_respects_user_preference_and_force():
    assert should_research("integrate the Stripe API", use_nexus=False) == (False, "nexus_disabled_by_request")
    ok, reason = should_research("rename a local variable", force=True)
    assert ok is True and reason == "forced"


# --- default off: never calls web --------------------------------------------

def test_default_off_does_not_call_web_and_warns(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    client = _FakeClient()
    svc = AtlasPlanTimeResearchService(client=client)
    res = svc.research(requirement_text="Add OAuth2 integration with the Stripe API", pool_id="p1")
    assert res.eligible is True and res.called is False
    assert res.status == "skipped"
    assert "web_research_disabled" in res.warnings
    assert client.calls == []  # no external call, no fabricated evidence


def test_ineligible_request_does_not_call_web(monkeypatch):
    monkeypatch.setenv(ENV, "1")  # enabled, but request is ineligible
    client = _FakeClient()
    svc = AtlasPlanTimeResearchService(client=client)
    res = svc.research(requirement_text="rename a function", pool_id="p1")
    assert res.eligible is False and res.called is False
    assert client.calls == []


# --- enabled + eligible: bounded research ------------------------------------

def test_enabled_and_eligible_runs_bounded_research(monkeypatch):
    monkeypatch.setenv(ENV, "1")
    client = _FakeClient()
    svc = AtlasPlanTimeResearchService(client=client)
    res = svc.research(requirement_text="Add OAuth2 integration with the Stripe API", pool_id="p1", item_id="i1")
    assert res.eligible is True and res.called is True
    assert len(client.calls) == 1
    assert client.calls[0].query.startswith("Add OAuth2")
    assert client.calls[0].purpose == "web_research"
    assert "libfoo" in res.summary
    assert res.findings and res.findings[0]["title"] == "libfoo docs"
    assert res.advisory is True  # advisory context, never authoritative
    md = res.to_metadata()
    assert md["advisory"] is True and md["called"] is True


def test_unavailable_research_returns_warning_without_failing(monkeypatch):
    monkeypatch.setenv(ENV, "1")
    client = _FakeClient(raises=True)
    svc = AtlasPlanTimeResearchService(client=client)
    res = svc.research(requirement_text="integrate the GitHub API", pool_id="p1")
    # The adapter swallows the client error into a warning pack; planning continues.
    assert res.eligible is True and res.called is True
    assert res.status in {"completed", "completed_with_warnings"}
    assert any("nexus_research_failed" in w or "plan_time_research_failed" in w for w in res.warnings)


def test_metadata_is_advisory_and_truthful_when_disabled(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    svc = AtlasPlanTimeResearchService(client=_FakeClient())
    md = svc.research(requirement_text="use the new WebSocket protocol").to_metadata()
    assert md["enabled"] is False
    assert md["called"] is False
    assert md["advisory"] is True
    assert "web_research_disabled" in md["warnings"]
