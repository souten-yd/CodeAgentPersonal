from pathlib import Path


def test_scale_89_docs_contract() -> None:
    t = "\n".join(Path(f).read_text(encoding="utf-8") for f in [
        "docs/atlas_development_handoff.md",
        "docs/atlas_scale_master_roadmap.md",
        "docs/atlas_unified_autopilot_checkpoint.md",
        "docs/atlas_autopilot_current_status.md",
        "docs/atlas_autopilot_scale_master_plan.md",
        "docs/atlas_thinui_readiness.md",
        "docs/atlas_autonomous_execution_readiness_policy.md",
    ])
    for s in [
        "PR-ATLAS-SCALE-89", "Current implementation PR:", "PR-ATLAS-SCALE-90", "Next implementation PR:", "PR-ATLAS-SCALE-91",
        "loop bound gate consolidation", "metadata-only", "does not run loops", "does not retry automatically", "does not continue automatically",
        "does not authorize automatic execution", "max actions per loop", "max retries", "max runtime", "max files changed", "max risk level",
        "max consecutive failures", "max verification attempts", "max patch transactions", "No unbounded autonomous loop", "Auto-continue remains disabled",
        "Execute-all remains forbidden", "Automatic loop execution remains disabled", "Automatic retry remains disabled", "Automatic stop execution remains disabled",
        "Automatic artifact capture remains disabled", "Automatic dry-run remains disabled", "Automatic approval remains disabled", "Automatic execute remains disabled",
        "Automatic verification remains disabled", "Automatic command execution remains disabled", "Automatic safe_apply remains disabled", "Automatic patch generation remains disabled",
        "Automatic patch apply remains disabled", "Automatic restore remains disabled", "Automatic rollback remains disabled", "Autonomous execution remains disabled",
        "Level 0 manual-only", "single existing manual action only", "PR-80 remains an out-of-order architecture checkpoint", "fully autonomous code agent", "Self-improving CodeAgentPersonal / KasaneCore",
    ]:
        assert s in t
    for s in ["PR-ATLAS-SCALE-90 completed", "loop_bound_ready authorizes automatic execution"]:
        assert s not in t
