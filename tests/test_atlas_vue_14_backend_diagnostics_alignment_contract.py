from app.atlas.workflow_state_contract import build_read_only_workflow_state


def test_vue_14_backend_diagnostics_alignment_contract() -> None:
    payload = build_read_only_workflow_state(
        goal='g', project_path='p', phase='read_only_preview', status='ok', primary_cta_label='Read-only'
    )
    diag = payload['diagnostics']
    assert diag['route_mounted'] is True
    assert diag['static_mount_deferred'] is False
    assert diag['route_path'] == '/atlas-next'
    assert diag['route_default'] is False
    assert diag['route_guarded'] is True
    assert diag['dist_backed'] is True
    assert diag['fail_closed'] is True
    assert 'unmounted' not in str(diag).lower()
    assert 'deferred' not in ' '.join(diag.get('warnings', [])).lower()
