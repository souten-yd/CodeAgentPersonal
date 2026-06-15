"""Atlas Git Steward.

Local Git development management for Atlas execution sessions.  The package
separates local repository operations from approval-bound remote publication.
"""

from agent.git_steward.contracts import (
    GitOperation,
    GitOperationClass,
    GitOperationDecision,
    GitRepositoryState,
    GitStewardResult,
    classify_git_operation,
    normalize_repo_path,
)
from agent.git_steward.local_adapter import (
    classify_external_publication,
    collect_diff,
    create_baseline_commit,
    create_local_commit,
    detect_repository,
    harden_ignore_policy,
    initialize_repository,
    prepare_branch,
)

__all__ = [
    "GitOperation",
    "GitOperationClass",
    "GitOperationDecision",
    "GitRepositoryState",
    "GitStewardResult",
    "classify_git_operation",
    "classify_external_publication",
    "collect_diff",
    "create_baseline_commit",
    "create_local_commit",
    "detect_repository",
    "harden_ignore_policy",
    "initialize_repository",
    "normalize_repo_path",
    "prepare_branch",
]
