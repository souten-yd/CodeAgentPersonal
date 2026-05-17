from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CHECKPOINT = DOCS / "atlas_unified_autopilot_checkpoint.md"

SCALE_MASTER_PLAN = DOCS / "atlas_autopilot_scale_master_plan.md"
DEV_TOOLING_DESIGN = DOCS / "atlas_dev_tooling_design.md"
AUTOMATION_DESIGN = DOCS / "atlas_autopilot_automation_design.md"
SAFETY_POLICY = DOCS / "atlas_autopilot_safety_policy.md"
CURRENT_STATUS = DOCS / "atlas_autopilot_current_status.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_scale_autopilot_design_docs_exist() -> None:
    for path in (
        SCALE_MASTER_PLAN,
        DEV_TOOLING_DESIGN,
        AUTOMATION_DESIGN,
        SAFETY_POLICY,
        CURRENT_STATUS,
    ):
        assert path.exists(), f"missing required scale autopilot doc: {path}"


def test_master_plan_contains_pr42_to_pr50_roadmap_and_mode_policy() -> None:
    text = read_text(SCALE_MASTER_PLAN)

    for term in (
        "PR-42",
        "PR-43",
        "PR-44",
        "PR-45",
        "PR-46",
        "PR-47",
        "PR-48",
        "PR-49",
        "PR-50",
        "local-first",
        "GitHub optional",
        "GitHub auth is only needed for remote operations",
    ):
        assert term in text


def test_dev_tooling_design_records_pr41_tools_and_pr42_targets() -> None:
    text = read_text(DEV_TOOLING_DESIGN)

    for term in (
        "git_status",
        "git_diff",
        "git_ls_files",
        "project_tree",
        "list_files",
        "file_outline",
        "symbol_index",
        "dependency_graph",
        "related_tests",
    ):
        assert term in text


def test_safety_policy_contains_forbidden_command_contracts() -> None:
    text = read_text(SAFETY_POLICY)

    for term in (
        "no arbitrary command execution",
        "shell=True",
        "remote git operations from read-only tools",
    ):
        assert term in text


def test_current_status_contains_completed_current_next_markers() -> None:
    text = read_text(CURRENT_STATUS)

    for term in (
        "PR-ATLAS-PIPE-0〜41",
        "PR-ATLAS-PIPE-41B",
        "PR-ATLAS-PIPE-42",
    ):
        assert term in text


def test_checkpoint_no_stale_or_duplicated_next_pr_markers() -> None:
    text = read_text(CHECKPOINT)

    assert "PR-ATLAS-PIPE-39C" not in text
    assert "PR-ATLAS-PIPE-40:" not in text
    assert text.count("## Next PR") == 1
