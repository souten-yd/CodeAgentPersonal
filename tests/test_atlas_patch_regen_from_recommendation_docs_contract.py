from pathlib import Path


def test_docs_and_ui_contract_tokens_present():
    docs = "\n".join(Path(p).read_text(encoding="utf-8") for p in [
        "docs/atlas_autopilot_scale_master_plan.md",
        "docs/atlas_autopilot_automation_design.md",
        "docs/atlas_autopilot_safety_policy.md",
        "docs/atlas_autopilot_current_status.md",
        "docs/atlas_unified_autopilot_checkpoint.md",
    ])
    assert "PR-ATLAS-PIPE-53" in docs
    assert "manual approval" in docs.lower()
    assert "no safe_apply" in docs.lower()
    assert "PR-ATLAS-PIPE-54" in docs
    ui = Path("ui.html").read_text(encoding="utf-8")
    assert "Patch Regen From Recommendation" in ui
    assert "This does not approve or apply the patch." in ui
    assert "Manual approval is still required." in ui


def test_no_arbitrary_command_shell_remote_git():
    sources = "\n".join(Path(p).read_text(encoding="utf-8") for p in [
        "agent/atlas_patch_regen_from_recommendation_service.py",
        "app/api/atlas_patch_regen_from_recommendation.py",
    ])
    assert "shell=True" not in sources
    assert "run_command" not in sources
    assert "git push" not in sources
    assert "git fetch" not in sources
    assert "git pull" not in sources
