from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_development_handoff.md",
    "docs/atlas_autonomous_execution_readiness_policy.md",
    "docs/atlas_thinui_readiness.md",
    "docs/atlas_vue_migration_plan.md",
]


def _section(text: str, marker: str) -> str:
    parts = text.split(f"## {marker}", 1)
    if len(parts) < 2:
        return text
    tail = parts[1]
    return tail.split("\n## ", 1)[0]


def test_docs_track_progression_and_no_stale_current_state():
    for doc in DOCS:
        text = Path(doc).read_text(encoding="utf-8")
        active = _section(text, "Active PR Pointer (Updated)")
        current = _section(text, "Current State")
        assert "Completed automation PR: PR-ATLAS-SCALE-108" in active
        assert "Current automation track: PR-ATLAS-SCALE-109" in active
        assert "Next automation track: PR-ATLAS-SCALE-109" in active
        assert "Planned UI track: return to PR-ATLAS-SCALE-109 automation track" in current
        assert "next work is PR-ATLAS-SCALE-109" in current
        active_head = "\n".join(active.splitlines()[:8])
        assert "- Completed automation PR: PR-ATLAS-SCALE-107" not in active_head
        assert "next PR may add local-only diff labels, not execution enable" not in current
