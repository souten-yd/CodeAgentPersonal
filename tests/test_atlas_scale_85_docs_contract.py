from pathlib import Path


def test_scale85_docs_contract() -> None:
    files = [
        "docs/atlas_scale_master_roadmap.md",
        "docs/atlas_development_handoff.md",
        "docs/atlas_unified_autopilot_checkpoint.md",
        "docs/atlas_autopilot_current_status.md",
        "docs/atlas_autopilot_scale_master_plan.md",
        "docs/atlas_thinui_readiness.md",
        "docs/atlas_autonomous_execution_readiness_policy.md",
    ]
    text = "\n".join(Path(f).read_text(encoding="utf-8") for f in files)
    must = [
        "PR-ATLAS-SCALE-85",
        "Current implementation PR:\n- PR-ATLAS-SCALE-86",
        "Next implementation PR:\n- PR-ATLAS-SCALE-87",
        "PR-84B fixed verification allowlist py_compile / node check contracts",
        "dry-run and approval gate consolidation",
        "metadata-only",
        "does not execute automatically",
        "Dry-run-first remains mandatory",
        "EXECUTE ONE ACTION remains required",
        "confirmation token or future equivalent approval token remains mandatory",
        "Explicit approval is mandatory for medium/high/strict risk",
        "strict_gate always requires explicit approval",
        "Missing or failed dry-run blocks readiness",
        "Automatic dry-run remains disabled",
        "Automatic approval remains disabled",
        "Automatic execute remains disabled",
        "Automatic verification remains disabled",
        "Automatic command execution remains disabled",
        "Automatic safe_apply remains disabled",
        "Automatic patch generation remains disabled",
        "Automatic patch apply remains disabled",
        "Automatic rollback remains disabled",
        "Autonomous execution remains disabled",
        "Level 0 manual-only",
        "Primary CTA remains single existing manual action only",
        "out-of-order architecture checkpoint",
        "fully autonomous code agent",
        "Self-improving CodeAgentPersonal / KasaneCore remains",
    ]
    for s in must:
        assert s in text
    for s in ["autonomous execution enabled", "approval automatic", "PR-ATLAS-SCALE-86 completed", "Current next PR"]:
        assert s not in text
