from pathlib import Path


def _section(text: str, start: str, end: str) -> str:
    s = text.index(start)
    e = text.index(end, s)
    return text[s:e]


def test_docs_pointers_updated():
    files = [
        'docs/atlas_development_handoff.md',
        'docs/atlas_unified_autopilot_checkpoint.md',
        'docs/atlas_autopilot_current_status.md',
        'docs/atlas_autopilot_scale_master_plan.md',
        'docs/atlas_scale_master_roadmap.md',
    ]
    text = '\n'.join(Path(f).read_text(encoding='utf-8') for f in files)
    assert 'PR-ATLAS-SCALE-66B' in text
    assert 'PR-ATLAS-SCALE-67: Planner Packaging v2 using Context Refresh v2 and PlanItem Impact Map' in text
    assert 'Context Refresh v2 using PlanItem Impact Map' in text
    assert 'advisory-only' in text
    assert 'no execution' in text

    handoff = Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')
    sec3 = _section(handoff, '## 3. Current PR Pointer', '## 4. Development Restart Instructions')
    sec4 = _section(handoff, '## 4. Development Restart Instructions', '## 5. Verification Checklist')

    active = sec3 + '\n' + sec4
    assert 'PR-ATLAS-SCALE-67: Planner Packaging v2 using Context Refresh v2 and PlanItem Impact Map' in active
    assert 'Current next PR:\nPR-ATLAS-SCALE-65' not in active
    assert 'Next implementation PR:\n- PR-ATLAS-SCALE-66' not in active
    assert 'Next implementation PR:\nPR-ATLAS-SCALE-66' not in active
