from pathlib import Path

def test_pr76c_diagnostics_drawer_structure_contract():
    html = Path('ui.html').read_text(encoding='utf-8')
    required = [
        'atlas-diagnostics-drawer','atlas-diagnostics-summary','atlas-diagnostics-raw-json-section',
        'atlas-diagnostics-subsystem-tools-section','atlas-diagnostics-ids-section','atlas-diagnostics-status'
    ]
    for rid in required:
        assert html.count(f'id="{rid}"') == 1
    assert 'id="atlas-diagnostics-drawer" class="atlas-panel-card atlas-surface-diagnostics"' in html
    assert 'id="atlas-diagnostics-raw-json-section" class="atlas-surface-diagnostics"' in html
    assert 'id="atlas-diagnostics-subsystem-tools-section" class="atlas-surface-diagnostics"' in html
    assert 'id="atlas-diagnostics-ids-section" class="atlas-surface-diagnostics"' in html
    assert '#atlas-dashboard[data-atlas-ui-mode="minimal"] .atlas-surface-diagnostics { display: none; }' in html
    d0=html.index('id="atlas-diagnostics-drawer"'); d1=html.index('</section>', d0)
    inner=html[d0:d1]
    for forbidden in ['id="atlas-status-grid"','id="atlas-workflow-shell"','id="atlas-current-item-card"','id="atlas-manual-loop-checklist"','PlanPool Overview','Pipeline Progress']:
        assert forbidden not in inner
    assert 'atlas-dashboard-42' in html
