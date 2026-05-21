from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_development_handoff.md",
    "docs/atlas_unified_autopilot_checkpoint.md",
    "docs/atlas_autopilot_current_status.md",
    "docs/atlas_autopilot_scale_master_plan.md",
    "docs/atlas_thinui_readiness.md",
]


def test_scale_82_docs_contract() -> None:
    text = "\n".join(Path(p).read_text(encoding="utf-8") for p in DOCS)
    for expected in [
        "PR-ATLAS-SCALE-82",
        "Current implementation PR:\n- PR-ATLAS-SCALE-83: Risk classification gate foundation",
        "Next implementation PR:\n- PR-ATLAS-SCALE-84: Verification allowlist gate foundation",
        "patch transaction and rollback metadata foundation",
        "metadata-only",
        "Automatic patch generation remains disabled",
        "Automatic patch apply remains disabled",
        "Automatic rollback remains disabled",
        "manual snapshot restore",
        "resolved data_root",
        "Level 0 manual-only",
        "Autonomous execution remains disabled",
        "EXECUTE ONE ACTION remains required",
        "Dry-run-first remains required",
        "PR-80 remains an out-of-order architecture checkpoint",
        "fully autonomous code agent",
        "Self-improving CodeAgentPersonal / KasaneCore",
    ]:
        assert expected in text
    for bad in [
        "autonomous execution is enabled",
        "patches are applied automatically",
        "rollback is automatic",
        "PR-ATLAS-SCALE-83 completed",
        "Current next PR",
    ]:
        assert bad not in text
