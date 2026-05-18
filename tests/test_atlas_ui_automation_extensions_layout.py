from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'ui.html').read_text(encoding='utf-8')


def atlas_block() -> str:
    return HTML.split('<!-- ATLAS MODE -->', 1)[1].split('<div class="agent-col mob-hidden"', 1)[0]


def test_automation_extensions_are_inside_details_and_panel_col() -> None:
    block = atlas_block()
    details_start = block.index('id="atlas-details-drawer"')
    details_end = block.index('</details>', details_start)
    section_idx = block.index('id="atlas-automation-extensions-panel"')
    panel_col_start = block.index('id="atlas-panel-col"')
    assert details_start < section_idx < details_end
    assert panel_col_start < section_idx
    assert 'id="atlas-automation-extensions-title"' in block


def test_automation_extensions_not_leaked_after_html_close() -> None:
    assert '</html>\n\n<section id="atlas-multi-item-autopilot-panel"' not in HTML
    assert '</html>\n\n<div id="bounded-retry-panel"' not in HTML


def test_automation_extension_tokens_exist_only_in_details_block() -> None:
    block = atlas_block()
    details_start = block.index('id="atlas-details-drawer"')
    details_end = block.index('<div class="atlas-legacy-compat"', details_start)
    details_block = block[details_start:details_end]
    for token in (
        'Multi-item Autopilot',
        'Context Refresh',
        'Bounded Retry',
        'Supervised Patch Regeneration',
        'Patch Candidate Approval',
        'Supervised Handoff Safe Apply',
    ):
        assert token in details_block


def test_extension_panels_have_expected_dom_ids() -> None:
    block = atlas_block()
    for token in (
        'id="atlas-automation-extensions-panel"',
        'id="atlas-multi-item-autopilot-panel"',
        'id="atlas-context-refresh-panel"',
        'id="bounded-retry-panel"',
        'id="atlas-patch-regen-panel"',
    ):
        assert token in block
