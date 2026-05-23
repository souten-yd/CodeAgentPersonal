from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def _canonical_section(text: str) -> str:
    start = text.index('## Current Atlas Vue UI Track State')
    end = text.find('\n## ', start + 1)
    return text[start:] if end == -1 else text[start:end]


def test_scale_93c_canonical_current_state_and_tracks() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        section = _canonical_section(text)
        assert ('Current automation track: PR-ATLAS-SCALE-96' in section) or ('Current automation track: PR-ATLAS-SCALE-98' in section) or ('Current automation track: PR-ATLAS-SCALE-99' in section) or ('Current automation track: PR-ATLAS-SCALE-101' in section) or (('Current automation track: PR-ATLAS-SCALE-103' if 'Current automation track: PR-ATLAS-SCALE-103' in section else 'Current automation track: PR-ATLAS-SCALE-105') in section)
        assert ('Next automation track: PR-ATLAS-SCALE-96' in text) or ('Completed automation PR: PR-ATLAS-SCALE-97' in text) or ('Next automation track: PR-ATLAS-SCALE-97' in text) or ('Current automation track: PR-ATLAS-SCALE-98' in text) or ('Current automation track: PR-ATLAS-SCALE-99' in text) or ('Current automation track: PR-ATLAS-SCALE-101' in text) or ('Next automation track: PR-ATLAS-SCALE-101' in text) or (('Current automation track: PR-ATLAS-SCALE-103' if 'Current automation track: PR-ATLAS-SCALE-103' in section else 'Current automation track: PR-ATLAS-SCALE-105') in text) or ('Next automation track: PR-ATLAS-SCALE-103' in text)
        assert 'SCALE-94 is disabled backend skeleton candidate only' in section
        assert 'VUE21 completed default-enable only, not execution-enable' in section
        assert 'legacy UI remains available via /ui/' in section
        assert 'runtime remains level_0_manual_only' in section
        assert 'Level-1 execution remains disabled' in section
        assert 'Vue execution capability remains none' in section


def test_scale_93c_stale_current_looking_vue_wording_removed_from_canonical_sections() -> None:
    stale = [
        'Current UI track: Vue defaultization complete: Atlas-specific Requirement Input / Start Atlas UI PR',
        'Planned UI track is PR-ATLAS-VUE-15 through PR-ATLAS-VUE-21',
        'PR-ATLAS-VUE-21 is the default enable checkpoint',
        'Existing ui.html remains default until PR-ATLAS-VUE-21',
        'Vue remains not default',
    ]
    for doc in DOCS:
        section = _canonical_section(Path(doc).read_text(encoding='utf-8'))
        for marker in stale:
            assert marker not in section
