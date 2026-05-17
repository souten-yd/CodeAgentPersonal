from pathlib import Path


def test_docs_include_pr43_and_43b():
    text = Path("docs/atlas_unified_autopilot_checkpoint.md").read_text(encoding="utf-8")
    assert "PR-ATLAS-PIPE-43" in text
    assert "PR-ATLAS-PIPE-43B" in text
