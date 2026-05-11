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
    assert 'max_sources: long64k ? 60 : 40' in text


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
