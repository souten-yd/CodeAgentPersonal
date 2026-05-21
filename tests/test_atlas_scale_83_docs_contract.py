from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_development_handoff.md",
    "docs/atlas_unified_autopilot_checkpoint.md",
    "docs/atlas_autopilot_current_status.md",
    "docs/atlas_autopilot_scale_master_plan.md",
    "docs/atlas_thinui_readiness.md",
    "docs/atlas_autonomous_execution_readiness_policy.md",
]


def test_scale_83_docs_contract() -> None:
    text = "\n".join(Path(p).read_text(encoding="utf-8") for p in DOCS)
    for expected in [
        "PR-ATLAS-SCALE-83",
        "Current implementation PR:\n- PR-ATLAS-SCALE-84: Verification allowlist gate foundation",
        "Next implementation PR:\n- PR-ATLAS-SCALE-85: Dry-run and approval gate consolidation",
        "risk classification gate foundation",
        "metadata-only",
        "does not authorize execution",
        "Unknown risk is not low risk",
        "strict-gate",
        "Automatic patch generation remains disabled",
        "Automatic patch apply remains disabled",
        "Automatic rollback remains disabled",
        "Automatic safe_apply remains disabled",
        "Automatic verification remains disabled",
        "Autonomous execution remains disabled",
        "Level 0 manual-only",
        "EXECUTE ONE ACTION remains required",
        "Dry-run-first remains required",
        "PR-80 remains an out-of-order architecture checkpoint",
        "fully autonomous code agent",
        "Self-improving CodeAgentPersonal / KasaneCore",
    ]:
        assert expected in text
    for bad in ["autonomous execution is enabled", "risk classification authorizes execution", "strict-gate bypassed", "PR-ATLAS-SCALE-84 completed", "Current next PR"]:
        assert bad not in text
