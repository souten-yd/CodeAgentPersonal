from __future__ import annotations

import re

from tests.helpers.ui_contract import load_root_ui_html_text, load_ui_contract_text


def _details_block(html: str) -> str:
    match = re.search(r'<details\s+id="nexus-research-advanced"[^>]*>(.*?)</details>', html, re.S)
    assert match, 'Advanced Settings details must exist'
    return match.group(1)


def test_ui_has_basic_research_fields_by_default() -> None:
    html = load_root_ui_html_text()
    before_advanced = html.split('<details id="nexus-research-advanced"', 1)[0]
    assert 'Query' in before_advanced
    assert 'Search Type' in before_advanced
    assert 'Depth' in before_advanced
    assert 'Start Research' in html
    assert 'max_queries' not in before_advanced
    assert 'continue_on_download_error' not in before_advanced
    assert 'Recursive Research' not in before_advanced


def test_advanced_settings_are_inside_details() -> None:
    block = _details_block(load_root_ui_html_text())
    assert 'Advanced Settings' in block
    for text in [
        'continue_on_download_error',
        'prefer_pdf',
        'official_first',
        'max_queries',
        'max_sources',
        'max_downloads',
        'Recursive Research',
        'max_iterations',
        'max_followup_queries',
        'confidence_threshold',
        'stop_when_sufficient',
    ]:
        assert text in block


def test_auto_settings_helper_exists_and_maps_depths() -> None:
    text = load_ui_contract_text()
    assert 'function resolveNexusResearchAutoSettings' in text
    assert re.search(r'deep:\s*\{[^}]*recursive_search:\s*true', text, re.S)
    assert re.search(r'quick:\s*\{[^}]*recursive_search:\s*false', text, re.S)
    assert 'max_sources: 100' in text


def test_compact_status_helper_hides_job_id_from_compact_lines() -> None:
    text = load_ui_contract_text()
    assert 'function formatNexusResearchStatusCompact' in text
    helper = text.split('function formatNexusResearchStatusCompact', 1)[1].split('\n}\n', 1)[0]
    assert 'job_id' not in helper
    assert 'Debug Details' in text


def test_answer_notice_classifier_does_not_warn_on_stop_without_truncation() -> None:
    text = load_ui_contract_text()
    assert 'function classifyNexusAnswerGenerationNotice' in text
    assert "finishReason === 'stop'" in text
    assert "severity: 'none'" in text
    assert '回答が出力上限で途中終了しました' in text


def test_fallback_role_warning_removed_from_normal_ui() -> None:
    text = load_ui_contract_text()
    assert 'role_model_search を設定してください。' not in text
    assert 'hasRoleWarning' not in text

def test_advanced_override_helpers_exist_and_guard_closed_details() -> None:
    text = load_ui_contract_text()
    assert 'function isNexusAdvancedSettingsOpen()' in text
    assert 'function collectNexusAdvancedOverrides()' in text
    helper = text.split('function collectNexusAdvancedOverrides()', 1)[1].split('\n}\n', 1)[0]
    assert 'if (!isNexusAdvancedSettingsOpen()) return {};' in helper
    assert "readInt('nexus-deep-max-queries', 1, 50)" in helper
    assert "readInt('nexus-deep-max-sources', 1, 200)" in helper
    assert "readInt('nexus-deep-max-downloads', 1, 200)" in helper


def test_run_deep_research_merges_auto_settings_before_advanced_overrides() -> None:
    text = load_ui_contract_text()
    run_body = text.split('async function runNexusDeepResearch()', 1)[1].split('\n}\n', 1)[0]
    auto_idx = run_body.index('const autoSettings')
    override_idx = run_body.index('const advancedOverrides')
    payload_idx = run_body.index('const payload = {')
    assert auto_idx < override_idx < payload_idx
    payload_block = run_body[payload_idx:run_body.index('};', payload_idx)]
    assert '...autoSettings' in payload_block
    assert '...advancedOverrides' in payload_block
    assert payload_block.index('...autoSettings') < payload_block.index('...advancedOverrides')


def test_run_deep_research_payload_does_not_always_include_advanced_fields_directly() -> None:
    text = load_ui_contract_text()
    run_body = text.split('async function runNexusDeepResearch()', 1)[1].split('\n}\n', 1)[0]
    payload_block = run_body.split('const payload = {', 1)[1].split('\n    };', 1)[0]
    for key in [
        'max_queries:',
        'max_results_per_query:',
        'max_sources:',
        'max_downloads:',
        'recursive_search:',
        'max_iterations:',
        'max_followup_queries:',
        'confidence_threshold:',
    ]:
        assert key not in payload_block


def test_closed_advanced_details_hidden_values_are_not_payload_sources() -> None:
    text = load_ui_contract_text()
    assert 'if (!isNexusAdvancedSettingsOpen()) return {};' in text
    assert 'const advancedOverrides = (typeof collectNexusAdvancedOverrides === \'function\')' in text
    assert 'window.__nexusAdvancedOverridesEnabled = false' in text
    assert "el.addEventListener('toggle'" in text
