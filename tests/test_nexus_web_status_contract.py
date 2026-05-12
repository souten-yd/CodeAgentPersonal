import app.nexus.router as r


def test_searxng_active_without_brave_key(monkeypatch):
    monkeypatch.setenv('NEXUS_WEB_SEARCH_PROVIDER','searxng')
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY', raising=False)
    monkeypatch.setenv('NEXUS_SEARXNG_URL','http://example.com')
    monkeypatch.setattr(r,'_check_searxng_connectivity',lambda url:(True,'ok'))
    d=r.nexus_web_status_compat()
    assert d['stub'] is False
    assert d['non_fatal'] is False
    assert 'brave' not in str(d.get('provider_errors',{})).lower()
    assert 'brave' not in d.get('message','').lower()


def test_braveapi_fallback_to_searxng(monkeypatch):
    monkeypatch.setenv('NEXUS_WEB_SEARCH_PROVIDER','braveapi')
    monkeypatch.setenv('NEXUS_SEARCH_FALLBACK_PROVIDERS','searxng')
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY', raising=False)
    monkeypatch.setattr(r,'_check_searxng_connectivity',lambda url:(True,'ok'))
    d=r.nexus_web_status_compat()
    assert d['stub'] is False
    assert d['active_provider'] == 'searxng'
    assert 'braveapi_unconfigured' in d.get('skipped_providers',[])
