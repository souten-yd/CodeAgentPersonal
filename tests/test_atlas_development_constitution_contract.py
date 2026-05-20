from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_constitution_exists() -> None:
    path = Path("docs/atlas_development_constitution.md")
    assert path.exists()
    text = _read(str(path))
    for token in [
        "shell=True",
        "remote git",
        'Path("ca_data")',
        "classic script",
        "inspect actual main branch files",
        "do not trust PR body alone",
    ]:
        assert token in text


def test_preflight_exists() -> None:
    path = Path("docs/atlas_preflight_checklist.md")
    assert path.exists()
    text = _read(str(path))
    for token in [
        "Confirm latest merged PR",
        "Inspect actual main branch files",
        "helper existence",
        "API registration",
        "UI binding",
        "cache bust",
    ]:
        assert token in text


def test_postflight_exists() -> None:
    path = Path("docs/atlas_postflight_checklist.md")
    assert path.exists()
    text = _read(str(path))
    for token in [
        "node --check",
        "grep",
        "checkpoint docs",
        "Current PR",
        "Next PR",
    ]:
        assert token in text


def test_pr_template_exists() -> None:
    path = Path("docs/atlas_pr_template.md")
    assert path.exists()
    text = _read(str(path))
    for token in [
        "Preflight Confirmation",
        "Safety Confirmation",
        "Postflight Confirmation",
        "Known Limitations",
        "Next PR",
    ]:
        assert token in text


def test_self_development_rules_exists() -> None:
    path = Path("docs/atlas_self_development_rules.md")
    assert path.exists()
    text = _read(str(path))
    for token in [
        "workspace snapshot",
        "restore point",
        "before hash manifest",
        "self-modification",
        "PR-73",
        "human approval",
    ]:
        assert token in text


def test_handoff_references_constitution() -> None:
    text = _read("docs/atlas_development_handoff.md")
    for token in [
        "atlas_development_constitution.md",
        "atlas_preflight_checklist.md",
        "atlas_postflight_checklist.md",
    ]:
        assert token in text


def test_checkpoint_current_next_pr() -> None:
    for path in [
        "docs/atlas_unified_autopilot_checkpoint.md",
        "docs/atlas_autopilot_current_status.md",
        "docs/atlas_autopilot_scale_master_plan.md",
    ]:
        text = _read(path)
        assert "PR-ATLAS-DOCS-CONSTITUTION-01" in text
        assert "PR-ATLAS-SCALE-64" in text
