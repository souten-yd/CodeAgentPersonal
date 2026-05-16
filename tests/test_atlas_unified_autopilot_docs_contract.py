from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MASTER_PLAN = DOCS / "atlas_unified_autopilot_master_plan.md"
CHECKPOINT = DOCS / "atlas_unified_autopilot_checkpoint.md"
DECISIONS = DOCS / "atlas_unified_autopilot_decisions.md"
PR_BACKLOG = DOCS / "atlas_unified_autopilot_pr_backlog.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_unified_autopilot_docs_exist() -> None:
    for path in (MASTER_PLAN, CHECKPOINT, DECISIONS, PR_BACKLOG):
        assert path.exists(), f"missing required Atlas unified Autopilot doc: {path}"


def test_master_plan_contains_required_contract_terms() -> None:
    text = read_text(MASTER_PLAN)

    for term in (
        "Task = PlanItem",
        "Agent = Autopilot",
        "Plan Pool",
        "Pipeline",
        "Nexus Research",
        "Atlas内部専用部品",
    ):
        assert term in text


def test_checkpoint_contains_required_continuation_headings() -> None:
    text = read_text(CHECKPOINT)

    for term in (
        "Current PR",
        "Next PR",
        "Important Constraints",
        "Known Current Code Facts",
    ):
        assert term in text


def test_decisions_contains_initial_adrs() -> None:
    text = read_text(DECISIONS)

    for term in ("ADR-001", "ADR-002", "ADR-003", "ADR-004", "ADR-005"):
        assert term in text


def test_pr_backlog_contains_initial_and_final_pipe_prs() -> None:
    text = read_text(PR_BACKLOG)

    for term in ("PR-ATLAS-PIPE-1", "PR-ATLAS-PIPE-15"):
        assert term in text
