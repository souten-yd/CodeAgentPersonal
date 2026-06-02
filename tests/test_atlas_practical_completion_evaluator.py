from __future__ import annotations

import json
from pathlib import Path

from agent.atlas_practical_completion_evaluator import (
    REQUIRED_PR_EVIDENCE,
    AtlasPracticalCompletionEvaluator,
)


def test_practical_completion_evaluator_requires_all_evidence() -> None:
    manifest = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    result = AtlasPracticalCompletionEvaluator().evaluate(
        {
            "completed_prs": REQUIRED_PR_EVIDENCE,
            "acceptance_tests_passed": True,
            "safety_grep_clean": True,
            "manifest_policy_docs_aligned": True,
        },
        manifest,
    )

    assert result["status"] == "accepted_with_evidence"
    assert result["complete"] is True
    assert result["missing_criteria"] == []
    assert result["direct_merge_enabled"] is False
    assert result["remote_git_push_enabled"] is False
    assert result["self_apply_enabled"] is False
    assert result["stable_runtime_mutation_enabled"] is False


def test_practical_completion_evaluator_blocks_missing_evidence() -> None:
    manifest = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    result = AtlasPracticalCompletionEvaluator().evaluate(
        {
            "completed_prs": ["PR-E"],
            "acceptance_tests_passed": False,
            "safety_grep_clean": True,
            "manifest_policy_docs_aligned": True,
        },
        manifest,
    )

    assert result["status"] == "corrective_checkpoint_in_progress"
    assert result["complete"] is False
    assert "PR-N" in result["missing_criteria"]
    assert "acceptance_tests_passed" in result["missing_criteria"]
