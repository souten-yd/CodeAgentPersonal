from tests.helpers.ui_contract import load_ui_contract_text


def _ui() -> str:
    return load_ui_contract_text()


def test_advanced_overrides_return_empty_when_advanced_settings_closed() -> None:
    html = _ui()
    assert 'if (!isNexusAdvancedSettingsOpen()) return {};' in html


def test_advanced_ui_clamps_match_expanded_api_limits() -> None:
    html = _ui()
    assert "readInt('nexus-deep-max-results-per-query', 1, 50)" in html
    assert "readInt('nexus-deep-max-sources', 1, 500)" in html
    assert "readInt('nexus-deep-max-download-mb', 1, 1000)" in html
    assert "readInt('nexus-deep-max-total-download-mb', 1, 8192)" in html
    assert "readInt('nexus-deep-max-downloads', 1, 500)" in html
    assert "readInt('nexus-deep-max-iterations', 1, 8)" in html
    assert "readInt('nexus-deep-max-followup-queries', 1, 20)" in html


def test_advanced_ui_results_clamp_is_not_legacy_100() -> None:
    html = _ui()
    assert "readInt('nexus-deep-max-results-per-query', 1, 100)" not in html
