from pathlib import Path


def test_scale_88_docs_contract() -> None:
    docs = "\n".join(Path(p).read_text(encoding="utf-8") for p in [
        "docs/atlas_scale_master_roadmap.md",
        "docs/atlas_development_handoff.md",
        "docs/atlas_unified_autopilot_checkpoint.md",
        "docs/atlas_autopilot_current_status.md",
        "docs/atlas_autopilot_scale_master_plan.md",
        "docs/atlas_thinui_readiness.md",
        "docs/atlas_autonomous_execution_readiness_policy.md",
    ])
    for s in [
        "PR-ATLAS-SCALE-88", "Current implementation PR:\n- PR-ATLAS-SCALE-89", "Next implementation PR:\n- PR-ATLAS-SCALE-90",
        "metadata-only", "does not stop real jobs", "does not kill processes", "not be fabricated",
        "future UI/CLI inspection", "No auto-continue after stop remains required", "Execute-all remains forbidden",
        "Automatic stop execution remains disabled", "Automatic artifact capture remains disabled",
        "Automatic dry-run remains disabled", "Automatic approval remains disabled", "Automatic execute remains disabled",
        "Automatic verification remains disabled", "Automatic command execution remains disabled",
        "Automatic safe_apply remains disabled", "Automatic patch generation remains disabled",
        "Automatic patch apply remains disabled", "Automatic restore remains disabled", "Automatic rollback remains disabled",
        "Autonomous execution remains disabled", "Level 0 manual-only", "single existing manual action only",
        "PR-80 remains an out-of-order architecture checkpoint", "fully autonomous code agent",
        "Self-improving CodeAgentPersonal / KasaneCore",
    ]:
        assert s in docs
