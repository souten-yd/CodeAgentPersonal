from pathlib import Path

def test_pr76c_cleanup_contract():
    html = Path('ui.html').read_text(encoding='utf-8')
    assert html.count('id="atlas-status-grid"') == 1
    seg = html[html.index('id="atlas-status-grid"')-120:html.index('id="atlas-status-grid"')+120]
    assert 'class="atlas-status-grid atlas-surface-minimal"' in seg
    assert 'id="atlas-automation-readiness-panel" class="atlas-panel-card atlas-surface-advanced"' in html
    for rid in ['atlas-operator-loop-queue-result','atlas-operator-loop-contract-result','atlas-operator-loop-executor-result','atlas-operator-loop-refresh-result','atlas-operator-loop-guarded-result']:
        ix=html.index(f'id="{rid}"')
        assert 'atlas-surface-diagnostics' in html[ix-120:ix+120]
    for rid in ['atlas-planpool-id','atlas-pipeline-run-id','atlas-operator-loop-pool-id','atlas-operator-loop-run-id','atlas-next-action-multi-status-run-id','atlas-patch-regen-from-rec-id']:
        assert f'id="{rid}"' in html
