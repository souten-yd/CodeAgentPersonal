from __future__ import annotations

from typing import Any


REQUIRED_PR_EVIDENCE = [
    "PR-E-0-G",
    "PR-E",
    "PR-F",
    "PR-G",
    "PR-H",
    "PR-I",
    "PR-J",
    "PR-K",
    "PR-L",
    "PR-M",
    "PR-N",
]

FORBIDDEN_FALSE_FLAGS = [
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "self_apply_enabled",
    "stable_runtime_mutation_enabled",
    "vue_source_of_truth",
    "default_conversational_shell_requires_vue",
    "default_conversational_shell_requires_vite",
]


class AtlasPracticalCompletionEvaluator:
    def evaluate(self, evidence: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
        completed = set(evidence.get("completed_prs") or [])
        missing = [pr for pr in REQUIRED_PR_EVIDENCE if pr not in completed]
        if not evidence.get("acceptance_tests_passed"):
            missing.append("acceptance_tests_passed")
        if not evidence.get("safety_grep_clean"):
            missing.append("safety_grep_clean")
        if not evidence.get("manifest_policy_docs_aligned"):
            missing.append("manifest_policy_docs_aligned")
        for flag in FORBIDDEN_FALSE_FLAGS:
            if manifest.get(flag) is not False:
                missing.append(f"{flag}_must_remain_false")
        complete = not missing
        return {
            "status": "accepted_with_evidence" if complete else "corrective_checkpoint_in_progress",
            "complete": complete,
            "missing_criteria": missing,
            "required_prs": REQUIRED_PR_EVIDENCE,
            "forbidden_flags_checked": FORBIDDEN_FALSE_FLAGS,
            "runtime_level_semantics": manifest.get("current_level_semantics", ""),
            "direct_merge_enabled": False,
            "remote_git_push_enabled": False,
            "self_apply_enabled": False,
            "stable_runtime_mutation_enabled": False,
        }
