"""Git API router (extracted from main.py).

Thin HTTP wrappers over the git helper functions that still live in ``main`` (``git_status``,
``git_commit``, ``git_checkout_branch``, ``git_reset``, ``git_diff``, ``_git_run``). Those helpers
are defined late in ``main.py`` and ``_git_run`` is shared by ~40 other call sites, so they are
imported lazily inside each handler (at request time, when ``main`` is fully loaded) rather than at
module import time. This keeps the extraction behavior-preserving; moving the helpers themselves into
a service module is a later, separate step (see docs/MAINTAINABILITY_PLAN.md).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["git"])


@router.get("/git/status")
def git_status_api(project: str = "default"):
    from main import git_status
    return {"status": git_status(project), "project": project}


@router.post("/git/commit")
def git_commit_api(req: dict):
    from main import git_commit
    project = req.get("project", "default")
    message = req.get("message", "CodeAgent commit")
    return {"result": git_commit(message, project)}


@router.post("/git/checkout")
def git_checkout_api(req: dict):
    from main import git_checkout_branch
    project = req.get("project", "default")
    name = req.get("name", "")
    create = req.get("create", True)
    if not name:
        raise HTTPException(400, "branch name required")
    return {"result": git_checkout_branch(name, create, project)}


@router.post("/git/reset")
def git_reset_api(req: dict):
    from main import git_reset
    project = req.get("project", "default")
    mode = req.get("mode", "hard")
    return {"result": git_reset(mode, project)}


@router.get("/git/diff")
def git_diff_api(project: str = "default", path: str = ""):
    from main import git_diff
    return {"diff": git_diff(path, project)}


@router.get("/git/log")
def git_log_api(project: str = "default", limit: int = 10):
    from main import WORK_DIR, _git_run
    cwd = os.path.join(WORK_DIR, project)
    if not os.path.exists(os.path.join(cwd, ".git")):
        return {"log": "no git repository", "commits": []}
    rc, out, err = _git_run(
        ["log", f"--max-count={limit}", "--pretty=format:%h|%s|%an|%ar"],
        cwd
    )
    commits = []
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({"hash": parts[0], "message": parts[1],
                                 "author": parts[2], "when": parts[3]})
    return {"commits": commits}
