from pathlib import Path


def test_static_structure_order_and_diagnostics_bounds():
    html = Path('ui.html').read_text(encoding='utf-8')
    ids_in_order = [
        'atlas-workflow-shell',
        'atlas-status-grid',
        'atlas-diagnostics-drawer',
        'atlas-planpool-id',
        'atlas-pipeline-status',
        'atlas-current-item-card',
        'atlas-details-drawer',
    ]
    positions = []
    for sid in ids_in_order:
        needle = f'id="{sid}"'
        assert needle in html, f"missing {sid}"
        positions.append(html.index(needle))
    assert positions == sorted(positions)

    diag_start = html.index('id="atlas-diagnostics-drawer"')
    diag_end = html.index('</section>', diag_start)
    for sid in ['atlas-planpool-id', 'atlas-pipeline-status', 'atlas-current-item-card']:
        assert html.index(f'id="{sid}"') > diag_end
