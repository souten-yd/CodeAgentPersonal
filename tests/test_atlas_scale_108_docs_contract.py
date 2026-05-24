from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_development_handoff.md",
    "docs/atlas_autonomous_execution_readiness_policy.md",
    "docs/atlas_thinui_readiness.md",
    "docs/atlas_vue_migration_plan.md",
]


def _section_required(text: str, heading: str) -> str:
    marker = f"## {heading}"
    assert marker in text, f"missing section: {heading}"
    tail = text.split(marker, 1)[1]
    next_idx = tail.find("\n## ")
    return tail[:next_idx] if next_idx != -1 else tail


def test_roadmap_sections_are_strict_and_track_progression():
    text = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")
    active = _section_required(text, "Active PR Pointer (Updated)")
    current = _section_required(text, "Current Atlas Vue UI Track State")

    assert "Completed automation PR: PR-ATLAS-SCALE-111" in active
    assert "Current automation track: PR-ATLAS-SCALE-112" in active
    assert "Next automation track: PR-ATLAS-SCALE-112" in active
    assert "Planned UI track: return to PR-ATLAS-SCALE-112 automation track" in current
    assert "next work is PR-ATLAS-SCALE-112" in current

    assert "Completed automation PR: PR-ATLAS-SCALE-109" not in active
    assert "Current automation track: PR-ATLAS-SCALE-111" not in active
    assert "Next automation track: PR-ATLAS-SCALE-111" not in active
    assert "Current automation track: PR-ATLAS-SCALE-111" not in current
    assert "Next automation track: PR-ATLAS-SCALE-111" not in current
    assert "next PR may add local-only diff labels, not execution enable" not in current
    assert "Level-1 execution remains disabled" in text


def test_docs_track_progression_and_no_stale_current_state_tokens():
    for doc in DOCS:
        text = Path(doc).read_text(encoding="utf-8")
        assert "Completed automation PR: PR-ATLAS-SCALE-111" in text
        assert "Current automation track: PR-ATLAS-SCALE-112" in text
        assert "Next automation track: PR-ATLAS-SCALE-112" in text
        assert "Planned UI track: return to PR-ATLAS-SCALE-112 automation track" in text
        assert "next work is PR-ATLAS-SCALE-112" in text
        assert "next PR may add local-only diff labels, not execution enable" not in text
