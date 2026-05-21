from pathlib import Path


def test_scale84b_docs_contract() -> None:
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
        "PR-ATLAS-SCALE-84B",
        "Current implementation PR:\n- PR-ATLAS-SCALE-85",
        "Next implementation PR:\n- PR-ATLAS-SCALE-86",
        "verification allowlist py_compile / node check contracts",
        "python -m py_compile <safe relative file> is allowlisted metadata only",
        "node --check web/js/<safe js file> is allowlisted metadata only",
        "Targeted pytest -q tests/<safe test file>.py is allowlisted metadata only",
        "does not execute commands",
        "future guarded/manual verification eligibility",
        "Automatic verification remains disabled",
        "Automatic command execution remains disabled",
        "Automatic safe_apply remains disabled",
        "Automatic patch generation remains disabled",
        "Automatic patch apply remains disabled",
        "Automatic rollback remains disabled",
        "Autonomous execution remains disabled",
        "Level 0 manual-only remains",
        "EXECUTE ONE ACTION remains required",
        "Dry-run-first remains required",
        "out-of-order architecture checkpoint",
        "fully autonomous code agent",
        "Self-improving CodeAgentPersonal / KasaneCore remains in scope",
    ]
    for marker in must:
        assert marker in text

    forbidden = [
        "autonomous execution enabled",
        "verification commands are executed",
        "automatic verification enabled",
        "allowlist authorizes execution",
        "PR-ATLAS-SCALE-85 completed",
        "Current next PR",
    ]
    for marker in forbidden:
        assert marker not in text
