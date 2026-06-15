"""Atlas Git Steward contracts and authority classifier."""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

GIT_STEWARD_CONTRACT_VERSION = "atlas.git_steward.v1"


class GitStewardModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GitOperationClass(StrEnum):
    LOCAL_READ = "local_read"
    LOCAL_WRITE = "local_write"
    REMOTE_READ = "remote_read"
    REMOTE_PUBLICATION = "remote_publication"
    REMOTE_ADMIN = "remote_admin"


class GitOperation(GitStewardModel):
    schema_version: str = GIT_STEWARD_CONTRACT_VERSION
    operation: str = Field(min_length=1)
    target: str = ""
    operation_class: GitOperationClass
    atlas_owned_scope: bool = True


class GitOperationDecision(GitStewardModel):
    schema_version: str = GIT_STEWARD_CONTRACT_VERSION
    operation: str
    operation_class: GitOperationClass
    approval_required: bool
    allowed_without_approval: bool
    reasons: list[str] = Field(default_factory=list)


class GitRepositoryState(GitStewardModel):
    path: str
    exists: bool
    git_dir: str = ""
    branch: str = ""
    head_sha: str = ""
    dirty: bool = False
    untracked_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)


class GitStewardResult(GitStewardModel):
    operation: str
    status: str = "ok"  # ok | blocked | approval_needed | unavailable
    approval_required: bool = False
    branch: str = ""
    commit_sha: str = ""
    diff_ref: str = ""
    worktree_path: str = ""
    changed_files: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def normalize_repo_path(path: str | Path) -> Path:
    return Path(path).resolve()


_LOCAL_READ = {"status", "diff", "log", "show", "rev-parse", "branch-list"}
_LOCAL_WRITE = {"init", "checkout", "branch", "worktree", "add", "commit", "stash", "restore", "reset-atlas-scope"}
_REMOTE_READ = {"fetch", "pull", "clone", "remote-show"}
_REMOTE_PUBLICATION = {"push", "push-tag", "create-pr", "create-remote-branch"}
_REMOTE_ADMIN = {"delete-remote-branch", "merge-pr", "force-push"}


DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".env",
    "*.key",
    "*.pem",
    "credentials.*",
    "secrets.*",
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "dist/",
    "build/",
    "ca_data/",
    "logs/",
    "*.sqlite3",
    "*.db",
    "*.gguf",
    "*.safetensors",
    "*.pt",
    "*.onnx",
)


def classify_git_operation(operation: str, *, atlas_owned_scope: bool = True) -> GitOperationDecision:
    """Classify Git operation authority.

    Local repository management and remote reads are allowed without approval.
    Remote publication and remote administration require approval.
    Local state-changing operations are only free in Atlas-owned scope.
    """
    op = operation.strip().lower()
    if op in _LOCAL_READ:
        cls = GitOperationClass.LOCAL_READ
        approval = False
        reasons = ["local_read"]
    elif op in _REMOTE_READ:
        cls = GitOperationClass.REMOTE_READ
        approval = False
        reasons = ["remote_read_only"]
    elif op in _LOCAL_WRITE:
        cls = GitOperationClass.LOCAL_WRITE
        approval = not atlas_owned_scope
        reasons = ["local_write", "atlas_owned_scope" if atlas_owned_scope else "outside_atlas_owned_scope"]
    elif op in _REMOTE_PUBLICATION:
        cls = GitOperationClass.REMOTE_PUBLICATION
        approval = True
        reasons = ["remote_publication"]
    elif op in _REMOTE_ADMIN:
        cls = GitOperationClass.REMOTE_ADMIN
        approval = True
        reasons = ["remote_admin"]
    else:
        cls = GitOperationClass.LOCAL_WRITE
        approval = True
        reasons = ["unknown_operation"]
    return GitOperationDecision(
        operation=operation,
        operation_class=cls,
        approval_required=approval,
        allowed_without_approval=not approval,
        reasons=reasons,
    )
