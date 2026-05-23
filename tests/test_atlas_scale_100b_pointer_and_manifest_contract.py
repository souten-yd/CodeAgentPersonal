import json
from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def test_scale_100b_pointer_alignment():
    all_text = []
    for d in DOCS:
        t = Path(d).read_text(encoding='utf-8')
        all_text.append(t)
        assert 'Completed automation PR: PR-ATLAS-SCALE-101' in t
        assert 'Current automation track: PR-ATLAS-SCALE-103' in t
        assert 'Next automation track: PR-ATLAS-SCALE-103' in t
    merged = '\\n'.join(all_text).lower()
    assert 'next work is pr-atlas-scale-102' in merged
    assert 'next work is pr-atlas-scale-100' not in merged
    assert 'planned ui track: return to pr-atlas-scale-100 automation track' not in merged


def test_scale_100b_manifest_guardrails_still_disabled():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['level1_execution_enabled'] is False
    assert m['level1_backend_skeleton_execution_enabled'] is False
    assert m['level1_callable_execution_endpoint_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
