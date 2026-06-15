"""Atlas Git Steward.

Local Git development management for Atlas execution sessions.  The package
separates local repository operations from approval-bound remote publication.
"""

from agent.git_steward.contracts import GitOperation, GitOperationClass, GitOperationDecision, classify_git_operation

__all__ = [
    "GitOperation",
    "GitOperationClass",
    "GitOperationDecision",
    "classify_git_operation",
]
