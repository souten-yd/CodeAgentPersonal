from pathlib import Path
DOCS='\n'.join(Path(p).read_text() for p in [
'docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md','docs/atlas_vue_migration_plan.md'])

def test_docs_scale_103_state_and_104_next_track():
    required=[
        'PR-ATLAS-SCALE-103 completed',
        'Completed automation PR: PR-ATLAS-SCALE-103',
        'Current automation track: PR-ATLAS-SCALE-106',
        'Next automation track: PR-ATLAS-SCALE-104',
    ]
    for token in required:
        assert token in DOCS


def test_docs_forbid_stale_scale_103_current_state_lines():
    forbidden = [
        'Planned UI track: return to PR-ATLAS-SCALE-103 automation track',
        'next work is PR-ATLAS-SCALE-103',
        'PR-ATLAS-SCALE-103 may add local-only history diff view',
    ]
    for token in forbidden:
        assert token not in DOCS


def test_docs_require_scale_104_next_work_and_ui_track():
    required = [
        'Planned UI track: return to PR-ATLAS-SCALE-106 automation track',
        'next work is PR-ATLAS-SCALE-106',
        'PR-ATLAS-SCALE-104 may add local-only diff filtering/grouping',
        'backend workflow_state remains authoritative',
    ]
    for token in required:
        assert token in DOCS
